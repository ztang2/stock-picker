"""Risk management: stop-loss monitoring, position sizing, and P&L tracking.

Rules:
- Stop-loss: alert when any position drops >15% from entry price
- Position limit: no single stock should exceed 20% of total portfolio value
- Tracks win/loss ratio and average gain/loss
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
RISK_CONFIG_FILE = DATA_DIR / "risk_config.json"
TRADE_HISTORY_FILE = DATA_DIR / "trade_history.json"

# Defaults
# Module-level sector cache (loaded once per process)
_sector_cache: Dict[str, str] = {}
_sector_cache_loaded = False


def _get_sector_cache() -> Dict[str, str]:
    global _sector_cache, _sector_cache_loaded
    if _sector_cache_loaded:
        return _sector_cache
    try:
        scan_file = DATA_DIR / "scan_results.json"
        if scan_file.exists():
            scan = json.loads(scan_file.read_text())
            for s in scan.get("all_scores", []):
                if s.get("sector"):
                    _sector_cache[s["ticker"]] = s["sector"]
    except Exception:
        pass
    _sector_cache_loaded = True
    return _sector_cache


DEFAULT_STOP_LOSS_PCT = -15.0  # Alert when down 15%
DEFAULT_MAX_POSITION_PCT = 20.0  # No single stock > 20% of portfolio
DEFAULT_TRAILING_STOP_PCT = -10  # Trailing stop: sell if price drops 10% from peak


def load_risk_config() -> dict:
    """Load risk management configuration."""
    defaults = {
        "stop_loss_pct": DEFAULT_STOP_LOSS_PCT,
        "max_position_pct": DEFAULT_MAX_POSITION_PCT,
        "trailing_stop_pct": DEFAULT_TRAILING_STOP_PCT,
    }
    if RISK_CONFIG_FILE.exists():
        try:
            cfg = json.loads(RISK_CONFIG_FILE.read_text())
            defaults.update(cfg)
        except Exception:
            pass
    return defaults


def _get_current_prices(tickers: List[str]) -> Dict[str, float]:
    """Fetch current prices for a list of tickers."""
    prices = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if price:
                prices[t] = float(price)
        except Exception:
            pass
    return prices


def check_stop_losses(holdings: Dict[str, dict], prices: Optional[Dict[str, float]] = None) -> List[dict]:
    """Check all positions against stop-loss thresholds.
    
    Returns list of alerts for positions that have breached stop-loss.
    """
    if not holdings:
        return []

    config = load_risk_config()
    stop_loss_pct = config["stop_loss_pct"]
    
    if prices is None:
        prices = _get_current_prices(list(holdings.keys()))

    alerts = []
    for ticker, pos in holdings.items():
        entry_price = pos.get("entry_price", 0)
        if not entry_price or entry_price <= 0:
            continue
        
        current_price = prices.get(ticker)
        if current_price is None:
            continue
        
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        
        alert = {
            "ticker": ticker,
            "entry_price": entry_price,
            "current_price": round(current_price, 2),
            "pnl_pct": round(pnl_pct, 2),
            "shares": pos.get("shares", 0),
            "pnl_dollar": round((current_price - entry_price) * pos.get("shares", 0), 2),
            "entry_date": pos.get("entry_date"),
            "stop_loss_threshold": stop_loss_pct,
        }
        
        if pnl_pct <= stop_loss_pct:
            alert["status"] = "STOP_LOSS_TRIGGERED"
            alert["urgency"] = "HIGH"
            alert["message"] = f"🔴 {ticker} down {pnl_pct:.1f}% — breached {stop_loss_pct}% stop-loss! Consider selling."
            alerts.append(alert)
        elif pnl_pct <= stop_loss_pct + 5:  # Within 5% of stop loss
            alert["status"] = "APPROACHING_STOP_LOSS"
            alert["urgency"] = "MEDIUM"
            alert["message"] = f"🟡 {ticker} down {pnl_pct:.1f}% — approaching {stop_loss_pct}% stop-loss."
            alerts.append(alert)
        else:
            alert["status"] = "OK"
            alert["urgency"] = "NONE"
            alerts.append(alert)
    
    return alerts


# --- Trailing Stop ---

TRAILING_STOP_FILE = DATA_DIR / "trailing_stops.json"

# Energy tickers that need trailing stop monitoring
ENERGY_TICKERS = {"CF", "EQT", "CTRA", "XOM", "CVX", "COP", "EOG", "DVN", "RRC", "OXY", "AR", "MPC", "VLO", "PSX"}


def _load_trailing_stops() -> dict:
    if TRAILING_STOP_FILE.exists():
        try:
            return json.loads(TRAILING_STOP_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_trailing_stops(data: dict):
    TRAILING_STOP_FILE.write_text(json.dumps(data, indent=2, default=str))


def check_trailing_stops(holdings: Dict[str, dict], prices: Optional[Dict[str, float]] = None) -> List[dict]:
    """Check trailing stops for energy stocks.
    
    Tracks the highest price since purchase. If current price drops 
    more than trailing_stop_pct from the peak, triggers alert.
    
    Returns list of trailing stop alerts.
    """
    config = load_risk_config()
    trailing_pct = config.get("trailing_stop_pct", DEFAULT_TRAILING_STOP_PCT)
    
    if trailing_pct is None:
        return []
    
    if prices is None:
        prices = _get_current_prices(list(holdings.keys()))
    
    # Load high water marks
    hwm = _load_trailing_stops()
    alerts = []
    updated = False
    
    for ticker, pos in holdings.items():
        current_price = prices.get(ticker)
        if current_price is None:
            continue
        
        entry_price = pos.get("entry_price", 0)
        if not entry_price:
            continue
        
        # Update high water mark
        prev_high = hwm.get(ticker, {}).get("high", entry_price)
        if current_price > prev_high:
            prev_high = current_price
            hwm[ticker] = {
                "high": round(prev_high, 2),
                "high_date": datetime.now().strftime("%Y-%m-%d"),
                "entry_price": entry_price,
            }
            updated = True
        elif ticker not in hwm:
            hwm[ticker] = {
                "high": round(max(entry_price, current_price), 2),
                "high_date": pos.get("entry_date", "unknown"),
                "entry_price": entry_price,
            }
            updated = True
        
        # Check trailing stop
        drop_from_high = ((current_price - prev_high) / prev_high) * 100
        is_energy = ticker in ENERGY_TICKERS
        
        alert = {
            "ticker": ticker,
            "entry_price": entry_price,
            "current_price": round(current_price, 2),
            "high_price": round(prev_high, 2),
            "drop_from_high_pct": round(drop_from_high, 2),
            "trailing_stop_pct": trailing_pct,
            "is_energy": is_energy,
        }
        
        if drop_from_high <= trailing_pct:
            alert["status"] = "TRAILING_STOP_TRIGGERED"
            alert["urgency"] = "HIGH"
            label = " (ENERGY ⚡)" if is_energy else ""
            alert["message"] = (
                f"🔴 {ticker}{label} dropped {drop_from_high:.1f}% from peak ${prev_high:.2f} "
                f"→ ${current_price:.2f}. Trailing stop {trailing_pct}% breached!"
            )
            alerts.append(alert)
        elif drop_from_high <= trailing_pct + 3:  # Within 3% of trailing stop
            alert["status"] = "APPROACHING_TRAILING_STOP"
            alert["urgency"] = "MEDIUM"
            label = " (ENERGY ⚡)" if is_energy else ""
            alert["message"] = (
                f"🟡 {ticker}{label} down {drop_from_high:.1f}% from peak ${prev_high:.2f}. "
                f"Trailing stop at {trailing_pct}%."
            )
            alerts.append(alert)
    
    if updated:
        _save_trailing_stops(hwm)
    
    return alerts


# --- Oil Price Monitor ---

OIL_STATE_FILE = DATA_DIR / "oil_monitor.json"


def check_oil_price_alert(threshold_drop_pct: float = -15.0) -> Optional[dict]:
    """Monitor oil price for significant pullback from recent highs.
    
    Tracks oil (CL=F) high water mark. If oil drops more than 
    threshold_drop_pct from peak, triggers alert to consider 
    reducing energy positions.
    
    Returns alert dict or None.
    """
    try:
        oil = yf.Ticker("CL=F")
        hist = oil.history(period="3mo")
        if hist is None or hist.empty:
            return None
        
        current = float(hist["Close"].iloc[-1])
        peak = float(hist["Close"].max())
        peak_date = str(hist["Close"].idxmax().date())
        
        drop_pct = ((current - peak) / peak) * 100
        
        # Load/update state
        state = {}
        if OIL_STATE_FILE.exists():
            try:
                state = json.loads(OIL_STATE_FILE.read_text())
            except Exception:
                pass
        
        state.update({
            "current": round(current, 2),
            "peak": round(peak, 2),
            "peak_date": peak_date,
            "drop_from_peak_pct": round(drop_pct, 2),
            "checked_at": datetime.now().isoformat(),
        })
        OIL_STATE_FILE.write_text(json.dumps(state, indent=2))
        
        if drop_pct <= threshold_drop_pct:
            return {
                "status": "OIL_PULLBACK_ALERT",
                "urgency": "HIGH",
                "current": round(current, 2),
                "peak": round(peak, 2),
                "peak_date": peak_date,
                "drop_pct": round(drop_pct, 2),
                "message": (
                    f"🛢️ OIL PULLBACK ALERT: Oil dropped {drop_pct:.1f}% from peak "
                    f"${peak:.2f} ({peak_date}) → ${current:.2f}. "
                    f"Consider reducing energy positions (CF, EQT, CTRA)!"
                ),
            }
        elif drop_pct <= threshold_drop_pct + 5:
            return {
                "status": "OIL_WEAKENING",
                "urgency": "MEDIUM",
                "current": round(current, 2),
                "peak": round(peak, 2),
                "drop_pct": round(drop_pct, 2),
                "message": (
                    f"🟡 Oil down {drop_pct:.1f}% from peak ${peak:.2f}. "
                    f"Watching for further weakness."
                ),
            }
        
        return {
            "status": "OK",
            "current": round(current, 2),
            "peak": round(peak, 2),
            "drop_pct": round(drop_pct, 2),
        }
        
    except Exception as e:
        logger.warning(f"Oil price check failed: {e}")
        return None


CEASEFIRE_STATE_FILE = DATA_DIR / "ceasefire_monitor.json"

# Tickers sensitive to peace (energy beneficiaries that would dump on ceasefire)
ENERGY_TICKERS = {"CF", "EQT", "CTRA", "RRC", "OXY", "DVN", "XOM", "CVX", "AR", "CNX",
                  "FANG", "MPC", "VLO", "PSX", "HAL", "SLB", "BKR"}
# Tickers that rally on peace
PEACE_TICKERS = {"HST", "UAL", "DAL", "AAL", "LUV", "CCL", "RCL", "NCLH",
                 "MAR", "HLT", "BKNG", "ABNB", "EXPE"}


def check_ceasefire_signals() -> Optional[dict]:
    """Detect early warning signals of potential ceasefire / war de-escalation.
    
    Monitors:
    1. Oil price single-day drop > 5% (unusual without supply news)
    2. VIX drop > 10% in a day (fear unwinding)
    3. Defense stocks down + Travel stocks up (sector rotation = peace bet)
    
    Returns alert dict with urgency level, or None.
    """
    try:
        # Fetch latest data
        tickers_to_check = ["CL=F", "^VIX", "LMT", "NOC", "UAL", "DAL"]
        data = yf.download(tickers_to_check, period="5d", progress=False)
        if data is None or data.empty:
            return None
        
        signals = []
        signal_count = 0
        
        # 1. Oil single-day drop
        try:
            oil = data["Close"]["CL=F"].dropna()
            if len(oil) >= 2:
                oil_today = float(oil.iloc[-1])
                oil_yesterday = float(oil.iloc[-2])
                oil_change = ((oil_today - oil_yesterday) / oil_yesterday) * 100
                if oil_change <= -5:
                    signals.append(f"🛢️ Oil crashed {oil_change:.1f}% in one day (${oil_yesterday:.0f}→${oil_today:.0f})")
                    signal_count += 2  # Strong signal
                elif oil_change <= -3:
                    signals.append(f"🛢️ Oil dropped {oil_change:.1f}% (${oil_yesterday:.0f}→${oil_today:.0f})")
                    signal_count += 1
        except Exception:
            pass
        
        # 2. VIX drop
        try:
            vix = data["Close"]["^VIX"].dropna()
            if len(vix) >= 2:
                vix_today = float(vix.iloc[-1])
                vix_yesterday = float(vix.iloc[-2])
                vix_change = ((vix_today - vix_yesterday) / vix_yesterday) * 100
                if vix_change <= -10:
                    signals.append(f"📉 VIX crashed {vix_change:.1f}% ({vix_yesterday:.1f}→{vix_today:.1f}) — fear unwinding")
                    signal_count += 2
                elif vix_change <= -5:
                    signals.append(f"📉 VIX dropped {vix_change:.1f}% ({vix_yesterday:.1f}→{vix_today:.1f})")
                    signal_count += 1
        except Exception:
            pass
        
        # 3. Sector rotation: defense down + travel up
        try:
            defense_changes = []
            travel_changes = []
            for t in ["LMT", "NOC"]:
                s = data["Close"][t].dropna()
                if len(s) >= 2:
                    chg = ((float(s.iloc[-1]) - float(s.iloc[-2])) / float(s.iloc[-2])) * 100
                    defense_changes.append(chg)
            for t in ["UAL", "DAL"]:
                s = data["Close"][t].dropna()
                if len(s) >= 2:
                    chg = ((float(s.iloc[-1]) - float(s.iloc[-2])) / float(s.iloc[-2])) * 100
                    travel_changes.append(chg)
            
            if defense_changes and travel_changes:
                avg_defense = sum(defense_changes) / len(defense_changes)
                avg_travel = sum(travel_changes) / len(travel_changes)
                if avg_defense < -2 and avg_travel > 2:
                    signals.append(f"🔄 Sector rotation: Defense {avg_defense:+.1f}% / Travel {avg_travel:+.1f}% — peace bet")
                    signal_count += 2
        except Exception:
            pass
        
        # Save state
        state = {
            "checked_at": datetime.now().isoformat(),
            "signal_count": signal_count,
            "signals": signals,
        }
        try:
            CEASEFIRE_STATE_FILE.write_text(json.dumps(state, indent=2))
        except Exception:
            pass
        
        # Determine urgency
        if signal_count >= 4:
            urgency = "CRITICAL"
            msg = "🚨 CEASEFIRE WARNING — 多重信号指向战争可能结束！立即准备减仓能源股！"
        elif signal_count >= 2:
            urgency = "HIGH"  
            msg = "⚠️ 停火预警 — 市场出现异常信号，密切关注新闻"
        elif signal_count >= 1:
            urgency = "MEDIUM"
            msg = "🟡 注意：市场信号略有异常，继续观察"
        else:
            return {
                "status": "OK",
                "signal_count": 0,
                "message": "No ceasefire signals detected",
            }
        
        return {
            "status": "CEASEFIRE_WARNING",
            "urgency": urgency,
            "signal_count": signal_count,
            "signals": signals,
            "message": msg,
            "action": "Review energy positions (CF, EQT, CTRA). If ceasefire confirmed, sell within 30min-1hr.",
        }
        
    except Exception as e:
        logger.warning(f"Ceasefire signal check failed: {e}")
        return None


def check_position_limits(holdings: Dict[str, dict], prices: Optional[Dict[str, float]] = None,
                          extra_holdings: Optional[Dict[str, dict]] = None) -> List[dict]:
    """Check if any position exceeds the max position size limit.
    
    Args:
        holdings: Stock picker holdings
        extra_holdings: Non-picker holdings (e.g., NFLX) with same format
    """
    config = load_risk_config()
    max_pct = config["max_position_pct"]
    
    all_holdings = dict(holdings)
    if extra_holdings:
        all_holdings.update(extra_holdings)
    
    if not all_holdings:
        return []
    
    if prices is None:
        prices = _get_current_prices(list(all_holdings.keys()))
    
    # Calculate total portfolio value
    positions = []
    total_value = 0
    for ticker, pos in all_holdings.items():
        current_price = prices.get(ticker, pos.get("entry_price", 0))
        shares = pos.get("shares", 0)
        value = current_price * shares
        total_value += value
        positions.append({
            "ticker": ticker,
            "shares": shares,
            "current_price": round(current_price, 2),
            "value": round(value, 2),
            "entry_price": pos.get("entry_price", 0),
        })
    
    if total_value <= 0:
        return []
    
    alerts = []
    for p in positions:
        pct = (p["value"] / total_value) * 100
        p["portfolio_pct"] = round(pct, 1)
        p["max_allowed_pct"] = max_pct
        
        if pct > max_pct:
            p["status"] = "OVER_LIMIT"
            p["message"] = f"⚠️ {p['ticker']} is {pct:.1f}% of portfolio (limit: {max_pct}%). Consider trimming."
        else:
            p["status"] = "OK"
        
        alerts.append(p)
    
    # Sort by portfolio_pct descending
    alerts.sort(key=lambda x: x["portfolio_pct"], reverse=True)
    
    # Sector concentration check (max 35% per sector)
    MAX_SECTOR_PCT = 35.0
    sector_values = {}
    _sector_cache = _get_sector_cache()
    
    for p in alerts:
        ticker = p["ticker"]
        sector = _sector_cache.get(ticker) or all_holdings.get(ticker, {}).get("sector", "Unknown")
        p["sector"] = sector
        sector_values[sector] = sector_values.get(sector, 0) + p["value"]
    
    for p in alerts:
        sector = p.get("sector", "Unknown")
        sector_total = sector_values.get(sector, 0)
        sector_pct = (sector_total / total_value * 100) if total_value > 0 else 0
        p["sector_pct"] = round(sector_pct, 1)
        if sector_pct > MAX_SECTOR_PCT:
            if p.get("status") == "OK":
                p["status"] = "SECTOR_CONCENTRATED"
            p["sector_warning"] = f"⚠️ {sector} sector is {sector_pct:.0f}% of portfolio (limit: {MAX_SECTOR_PCT:.0f}%)"
    
    return alerts


def get_portfolio_summary(holdings: Dict[str, dict], prices: Optional[Dict[str, float]] = None,
                          extra_holdings: Optional[Dict[str, dict]] = None) -> dict:
    """Complete portfolio risk summary with stop-loss, position limits, and P&L."""
    all_holdings = dict(holdings)
    if extra_holdings:
        all_holdings.update(extra_holdings)
    
    if prices is None:
        prices = _get_current_prices(list(all_holdings.keys()))
    
    stop_loss_alerts = check_stop_losses(all_holdings, prices)
    position_alerts = check_position_limits(holdings, prices, extra_holdings)
    trailing_alerts = check_trailing_stops(all_holdings, prices)
    oil_alert = check_oil_price_alert()
    ceasefire_alert = check_ceasefire_signals()
    
    # P&L summary
    total_invested = 0
    total_current = 0
    winners = 0
    losers = 0
    total_win_pct = 0
    total_loss_pct = 0
    
    for ticker, pos in all_holdings.items():
        entry = pos.get("entry_price", 0)
        shares = pos.get("shares", 0)
        current = prices.get(ticker, entry)
        
        invested = entry * shares
        current_val = current * shares
        total_invested += invested
        total_current += current_val
        
        if current > entry:
            winners += 1
            total_win_pct += ((current - entry) / entry) * 100
        elif current < entry:
            losers += 1
            total_loss_pct += ((current - entry) / entry) * 100
    
    total_pnl = total_current - total_invested
    total_pnl_pct = ((total_current - total_invested) / total_invested * 100) if total_invested > 0 else 0
    avg_win = (total_win_pct / winners) if winners > 0 else 0
    avg_loss = (total_loss_pct / losers) if losers > 0 else 0
    win_rate = (winners / (winners + losers) * 100) if (winners + losers) > 0 else 0
    
    # Risk score (0-100, lower = riskier)
    risk_flags = 0
    stop_triggered = [a for a in stop_loss_alerts if a.get("status") == "STOP_LOSS_TRIGGERED"]
    stop_approaching = [a for a in stop_loss_alerts if a.get("status") == "APPROACHING_STOP_LOSS"]
    over_limit = [p for p in position_alerts if p.get("status") == "OVER_LIMIT"]
    
    trailing_triggered = [a for a in trailing_alerts if a.get("status") == "TRAILING_STOP_TRIGGERED"]
    
    risk_flags += len(stop_triggered) * 25
    risk_flags += len(stop_approaching) * 10
    risk_flags += len(over_limit) * 15
    risk_flags += len(trailing_triggered) * 20
    if oil_alert and oil_alert.get("status") == "OIL_PULLBACK_ALERT":
        risk_flags += 15
    if ceasefire_alert and ceasefire_alert.get("status") == "CEASEFIRE_WARNING":
        cf_urgency = ceasefire_alert.get("urgency", "")
        if cf_urgency == "CRITICAL":
            risk_flags += 30
        elif cf_urgency == "HIGH":
            risk_flags += 20
        elif cf_urgency == "MEDIUM":
            risk_flags += 10
    risk_score = max(0, 100 - risk_flags)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "portfolio_value": round(total_current, 2),
        "total_invested": round(total_invested, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "num_positions": len(all_holdings),
        "winners": winners,
        "losers": losers,
        "win_rate": round(win_rate, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "risk_score": risk_score,
        "stop_loss_alerts": stop_loss_alerts,
        "trailing_stop_alerts": trailing_alerts,
        "position_alerts": position_alerts,
        "oil_monitor": oil_alert,
        "ceasefire_monitor": ceasefire_alert,
        "warnings": {
            "stop_losses_triggered": len(stop_triggered),
            "approaching_stop_loss": len(stop_approaching),
            "over_position_limit": len(over_limit),
            "trailing_stops_triggered": len(trailing_triggered),
            "oil_pullback": oil_alert.get("status") == "OIL_PULLBACK_ALERT" if oil_alert else False,
            "ceasefire_warning": ceasefire_alert.get("status") == "CEASEFIRE_WARNING" if ceasefire_alert else False,
        },
    }


def record_trade(ticker: str, action: str, shares: float, price: float,
                 reason: str = "") -> None:
    """Record a trade for P&L tracking."""
    history = []
    if TRADE_HISTORY_FILE.exists():
        try:
            history = json.loads(TRADE_HISTORY_FILE.read_text())
        except Exception:
            pass
    
    history.append({
        "ticker": ticker,
        "action": action,  # BUY or SELL
        "shares": shares,
        "price": price,
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
    })
    
    TRADE_HISTORY_FILE.write_text(json.dumps(history, indent=2))


def get_trade_history() -> List[dict]:
    """Get all recorded trades."""
    if TRADE_HISTORY_FILE.exists():
        try:
            return json.loads(TRADE_HISTORY_FILE.read_text())
        except Exception:
            pass
    return []
