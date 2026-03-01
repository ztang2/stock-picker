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
DEFAULT_STOP_LOSS_PCT = -15.0  # Alert when down 15%
DEFAULT_MAX_POSITION_PCT = 20.0  # No single stock > 20% of portfolio
DEFAULT_TRAILING_STOP_PCT = None  # Optional trailing stop (not enabled by default)


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
    
    risk_flags += len(stop_triggered) * 25
    risk_flags += len(stop_approaching) * 10
    risk_flags += len(over_limit) * 15
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
        "position_alerts": position_alerts,
        "warnings": {
            "stop_losses_triggered": len(stop_triggered),
            "approaching_stop_loss": len(stop_approaching),
            "over_position_limit": len(over_limit),
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
