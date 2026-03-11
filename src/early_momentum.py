"""Early Momentum Score — predictive signals for stocks about to break out.

Combines 5 leading indicators into a composite score (0-10):
1. Analyst estimate revisions (upgrades vs downgrades)
2. Insider buying activity
3. Revenue acceleration (QoQ trend)
4. Institutional holdings changes
5. Earnings surprise (beat magnitude)

These are forward-looking signals available in real-time that help
identify stocks before they move, complementing the backward-looking
pipeline scores.
"""

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yfinance as yf
import numpy as np

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
MOMENTUM_CACHE_FILE = DATA_DIR / "early_momentum_cache.json"
CACHE_TTL_HOURS = 12


def _load_cache() -> dict:
    if MOMENTUM_CACHE_FILE.exists():
        try:
            return json.loads(MOMENTUM_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(data: dict):
    MOMENTUM_CACHE_FILE.write_text(json.dumps(data, indent=2, default=str))


def compute_early_momentum(ticker: str, force_refresh: bool = False) -> dict:
    """Compute Early Momentum Score for a single ticker.
    
    Returns dict with individual signal scores and composite (0-10).
    Score >= 6: potential breakout candidate
    Score >= 8: strong breakout signal
    """
    cache = _load_cache()
    cached = cache.get(ticker)
    if cached and not force_refresh:
        try:
            age = datetime.now() - datetime.fromisoformat(cached.get("cached_at", "2000-01-01"))
            if age < timedelta(hours=CACHE_TTL_HOURS):
                return cached
        except Exception:
            pass
    
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        
        signals = {}
        
        # 1. Analyst Estimate Revisions (+2 max)
        signals["analyst_revision"] = _score_analyst_revisions(tk, info)
        
        # 2. Insider Buying (+2 max)
        signals["insider_buying"] = _score_insider_activity(tk)
        
        # 3. Revenue Acceleration (+2 max)
        signals["revenue_acceleration"] = _score_revenue_acceleration(tk)
        
        # 4. Institutional Holdings Change (+2 max)
        signals["institutional_change"] = _score_institutional_change(info)
        
        # 5. Earnings Surprise (+2 max)
        signals["earnings_surprise"] = _score_earnings_surprise(tk)
        
        # Composite score (0-10)
        composite = sum(s["score"] for s in signals.values())
        
        # Determine signal
        if composite >= 8:
            momentum_signal = "STRONG_MOMENTUM"
        elif composite >= 6:
            momentum_signal = "MOMENTUM"
        elif composite >= 4:
            momentum_signal = "NEUTRAL"
        elif composite >= 2:
            momentum_signal = "WEAK"
        else:
            momentum_signal = "NO_MOMENTUM"
        
        result = {
            "ticker": ticker,
            "composite_score": round(composite, 1),
            "signal": momentum_signal,
            "signals": signals,
            "cached_at": datetime.now().isoformat(),
        }
        
        cache[ticker] = result
        _save_cache(cache)
        
        return result
        
    except Exception as e:
        logger.error(f"Early momentum failed for {ticker}: {e}")
        return {"ticker": ticker, "composite_score": 0, "signal": "ERROR", "error": str(e)}


def _score_analyst_revisions(tk, info: dict) -> dict:
    """Score based on analyst estimate revisions.
    
    Looks at:
    - Number of analysts upgrading vs downgrading
    - Price target vs current price (upside potential)
    - Recommendation trend
    
    Score: 0-2
    """
    score = 0.0
    details = {}
    
    try:
        # Price target upside
        current = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        target_median = info.get("targetMedianPrice")
        if current and target_median and current > 0:
            upside = (target_median - current) / current * 100
            details["target_upside_pct"] = round(upside, 1)
            # >30% upside = +1, >50% = +1.5
            if upside > 50:
                score += 1.5
            elif upside > 30:
                score += 1.0
            elif upside > 15:
                score += 0.5
        
        # Recommendation trend (upgrades)
        try:
            upgrades = tk.upgrades_downgrades
            if upgrades is not None and not upgrades.empty:
                # Look at last 30 days
                recent = upgrades.tail(10)
                ups = 0
                downs = 0
                for _, row in recent.iterrows():
                    action = str(row.get("Action", "")).lower()
                    if "up" in action or "initiated" in action or "reiterate" in action:
                        ups += 1
                    elif "down" in action:
                        downs += 1
                details["recent_upgrades"] = ups
                details["recent_downgrades"] = downs
                if ups > downs and ups >= 2:
                    score += 0.5
        except Exception:
            pass
            
    except Exception as e:
        details["error"] = str(e)
    
    return {"score": min(round(score, 1), 2.0), "details": details}


def _score_insider_activity(tk) -> dict:
    """Score based on insider buying/selling.
    
    Net insider buying is a strong bullish signal — management
    puts their own money where their mouth is.
    
    Score: 0-2
    """
    score = 0.0
    details = {}
    
    try:
        insider = tk.insider_transactions
        if insider is not None and not insider.empty:
            # Look at last 90 days
            buys = 0
            sells = 0
            buy_value = 0
            sell_value = 0
            
            for _, row in insider.iterrows():
                text = str(row.get("Text", "")).lower()
                shares = abs(row.get("Shares", 0) or 0)
                value = abs(row.get("Value", 0) or 0)
                
                if "purchase" in text or "buy" in text or "acquisition" in text:
                    buys += 1
                    buy_value += value
                elif "sale" in text or "sell" in text:
                    sells += 1
                    sell_value += value
            
            details["insider_buys"] = buys
            details["insider_sells"] = sells
            details["buy_value"] = buy_value
            details["sell_value"] = sell_value
            
            # Net buying
            if buys > 0 and buys >= sells:
                score += 1.0
                if buy_value > 1_000_000:  # >$1M in purchases
                    score += 0.5
                if buys >= 3:  # Multiple insiders buying
                    score += 0.5
            elif sells > buys * 2:  # Heavy selling
                score = 0
                
    except Exception as e:
        details["error"] = str(e)
    
    return {"score": min(round(score, 1), 2.0), "details": details}


def _score_revenue_acceleration(tk) -> dict:
    """Score based on revenue growth acceleration.
    
    Not just "is revenue growing" but "is growth ACCELERATING?"
    QoQ revenue growth rate increasing = very bullish.
    
    Score: 0-2
    """
    score = 0.0
    details = {}
    
    try:
        financials = tk.quarterly_financials
        if financials is not None and not financials.empty:
            # Get revenue row
            rev_row = None
            for idx in financials.index:
                if "revenue" in str(idx).lower() or "total revenue" in str(idx).lower():
                    rev_row = financials.loc[idx]
                    break
            
            if rev_row is not None and len(rev_row) >= 4:
                # Calculate QoQ growth rates
                revenues = [float(rev_row.iloc[i]) for i in range(min(4, len(rev_row))) if not np.isnan(float(rev_row.iloc[i]))]
                
                if len(revenues) >= 3:
                    # Revenues are most recent first
                    growth_rates = []
                    for i in range(len(revenues) - 1):
                        if revenues[i+1] > 0:
                            gr = (revenues[i] - revenues[i+1]) / revenues[i+1] * 100
                            growth_rates.append(gr)
                    
                    details["quarterly_growth_rates"] = [round(g, 1) for g in growth_rates]
                    
                    if len(growth_rates) >= 2:
                        # Is growth accelerating? (most recent > previous)
                        latest = growth_rates[0]
                        previous = growth_rates[1]
                        details["latest_qoq_growth"] = round(latest, 1)
                        details["previous_qoq_growth"] = round(previous, 1)
                        details["accelerating"] = latest > previous
                        
                        if latest > previous and latest > 0:
                            score += 1.0
                            acceleration = latest - previous
                            details["acceleration_ppt"] = round(acceleration, 1)
                            if acceleration > 5:  # >5 percentage points acceleration
                                score += 0.5
                            if latest > 15:  # Strong absolute growth too
                                score += 0.5
                        elif latest > 10:  # Not accelerating but still strong
                            score += 0.5
                            
    except Exception as e:
        details["error"] = str(e)
    
    return {"score": min(round(score, 1), 2.0), "details": details}


def _score_institutional_change(info: dict) -> dict:
    """Score based on institutional ownership signals.
    
    High institutional ownership + recent increases = smart money
    is accumulating.
    
    Score: 0-2
    """
    score = 0.0
    details = {}
    
    try:
        inst_pct = info.get("heldPercentInstitutions")
        insider_pct = info.get("heldPercentInsiders")
        short_pct = info.get("shortPercentOfFloat")
        
        if inst_pct is not None:
            details["institutional_pct"] = round(inst_pct * 100, 1)
            # High institutional = validation
            if inst_pct > 0.9:
                score += 0.5
            elif inst_pct > 0.7:
                score += 0.3
        
        if short_pct is not None:
            details["short_pct"] = round(short_pct * 100, 1)
            # Low short interest = less bearish pressure
            if short_pct < 0.03:
                score += 0.5
            elif short_pct < 0.05:
                score += 0.3
            # High short interest = potential short squeeze but also bearish
            elif short_pct > 0.15:
                details["short_squeeze_potential"] = True
                score += 0.3  # Slight positive for squeeze potential
        
        # Float utilization (institutional + insider coverage)
        if inst_pct and insider_pct:
            total_held = inst_pct + insider_pct
            details["total_held_pct"] = round(total_held * 100, 1)
            if total_held > 0.95:  # Tight float
                score += 0.5
                details["tight_float"] = True
        
        # Buyback indicator (shares outstanding decreasing)
        shares = info.get("sharesOutstanding")
        float_shares = info.get("floatShares")
        if shares and float_shares and float_shares < shares * 0.95:
            details["buyback_indicator"] = True
            score += 0.5
            
    except Exception as e:
        details["error"] = str(e)
    
    return {"score": min(round(score, 1), 2.0), "details": details}


def _score_earnings_surprise(tk) -> dict:
    """Score based on earnings surprise history.
    
    Consistent beats + increasing magnitude = strong signal.
    Companies that keep beating estimates tend to continue.
    
    Score: 0-2
    """
    score = 0.0
    details = {}
    
    try:
        earnings = tk.earnings_history
        if earnings is not None and not earnings.empty:
            surprises = []
            for _, row in earnings.iterrows():
                actual = row.get("epsActual")
                estimate = row.get("epsEstimate")
                if actual is not None and estimate is not None and estimate != 0:
                    surprise_pct = (actual - estimate) / abs(estimate) * 100
                    surprises.append(surprise_pct)
            
            if surprises:
                details["last_4q_surprises"] = [round(s, 1) for s in surprises[-4:]]
                
                # Count beats
                beats = sum(1 for s in surprises[-4:] if s > 0)
                details["beats_last_4q"] = beats
                
                if beats == 4:  # Perfect beat streak
                    score += 1.0
                elif beats >= 3:
                    score += 0.5
                
                # Most recent surprise magnitude
                if surprises:
                    latest = surprises[-1]
                    details["latest_surprise_pct"] = round(latest, 1)
                    if latest > 10:  # >10% beat
                        score += 1.0
                    elif latest > 5:
                        score += 0.5
                    elif latest < -5:  # Bad miss
                        score = max(0, score - 0.5)
                        
    except Exception as e:
        # Fallback to earnings_dates if earnings_history unavailable
        try:
            ed = tk.earnings_dates
            if ed is not None and not ed.empty:
                # Check for recent surprise
                for _, row in ed.iterrows():
                    surprise = row.get("Surprise(%)")
                    if surprise is not None and not np.isnan(surprise):
                        details["latest_surprise_pct"] = round(surprise, 1)
                        if surprise > 10:
                            score += 1.0
                        elif surprise > 5:
                            score += 0.5
                        break
        except Exception:
            pass
        details["fallback"] = True
    
    return {"score": min(round(score, 1), 2.0), "details": details}


# === Batch operations ===

def scan_top_momentum(n: int = 20) -> List[dict]:
    """Compute early momentum for top N stocks from latest scan.
    
    Returns list sorted by momentum score (highest first).
    """
    scan_file = DATA_DIR / "scan_results.json"
    if not scan_file.exists():
        return []
    
    try:
        scan_data = json.loads(scan_file.read_text())
        # Get all stocks, not just top N — momentum might be in lower-ranked stocks
        all_scores = scan_data.get("all_scores", [])
        # Take top 100 by composite score to check for momentum
        candidates = sorted(all_scores, key=lambda x: x.get("composite_score", 0), reverse=True)[:100]
        tickers = [s["ticker"] for s in candidates]
    except Exception:
        return []
    
    results = []
    for ticker in tickers:
        momentum = compute_early_momentum(ticker)
        if momentum.get("composite_score", 0) >= 4:  # Only include notable scores
            # Add scan data
            scan_info = next((s for s in candidates if s["ticker"] == ticker), {})
            momentum["scan_score"] = scan_info.get("composite_score", 0)
            momentum["scan_signal"] = scan_info.get("entry_signal", "?")
            momentum["sector"] = scan_info.get("sector", "?")
            results.append(momentum)
    
    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return results[:n]


def format_momentum_report(results: List[dict]) -> str:
    """Format momentum scan results as readable text."""
    if not results:
        return "No stocks with significant momentum signals found."
    
    lines = ["**🚀 Early Momentum Radar**\n"]
    
    for r in results:
        ticker = r["ticker"]
        score = r["composite_score"]
        signal = r["signal"]
        scan_score = r.get("scan_score", 0)
        sector = r.get("sector", "?")
        
        emoji = "🔥" if score >= 8 else "📈" if score >= 6 else "📊"
        lines.append(f"{emoji} **{ticker}** — Momentum: {score}/10 ({signal}) | Pipeline: {scan_score:.0f} | {sector}")
        
        signals = r.get("signals", {})
        details_parts = []
        
        ar = signals.get("analyst_revision", {})
        if ar.get("details", {}).get("target_upside_pct"):
            details_parts.append(f"Target +{ar['details']['target_upside_pct']:.0f}%")
        
        ib = signals.get("insider_buying", {})
        if ib.get("details", {}).get("insider_buys", 0) > 0:
            details_parts.append(f"Insiders buying ({ib['details']['insider_buys']})")
        
        ra = signals.get("revenue_acceleration", {})
        if ra.get("details", {}).get("accelerating"):
            details_parts.append(f"Rev accelerating ({ra['details'].get('latest_qoq_growth', 0):.0f}%)")
        
        es = signals.get("earnings_surprise", {})
        if es.get("details", {}).get("beats_last_4q", 0) >= 3:
            details_parts.append(f"Beat {es['details']['beats_last_4q']}/4 quarters")
        
        if details_parts:
            lines.append(f"  → {' | '.join(details_parts)}")
        lines.append("")
    
    return "\n".join(lines)
