"""Auto Profit-Taking Module: Tiered sell signals with beta-adjusted targets.

Profit-taking rules:
- Default: Tier 1 (+20%), Tier 2 (+30%), Tier 3 (+50%)
- High beta (>1.2): Tighter targets (+15%, +25%, +40%)
- Low beta (<0.6): Wider targets (+25%, +35%, +60%)

Tracks triggered tiers in data/profit_targets.json.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
PROFIT_TARGETS_FILE = DATA_DIR / "profit_targets.json"

# Default tier thresholds (gain % from entry)
DEFAULT_TIERS = {
    "tier1": 20.0,
    "tier2": 30.0,
    "tier3": 50.0,
}

# Beta-based tier adjustments
HIGH_BETA_TIERS = {
    "tier1": 15.0,
    "tier2": 25.0,
    "tier3": 40.0,
}

LOW_BETA_TIERS = {
    "tier1": 25.0,
    "tier2": 35.0,
    "tier3": 60.0,
}

HIGH_BETA_THRESHOLD = 1.2
LOW_BETA_THRESHOLD = 0.6

# Approaching threshold: within X% of next tier
APPROACHING_THRESHOLD = 3.0


def _load_profit_targets() -> dict:
    """Load profit targets state from disk."""
    if PROFIT_TARGETS_FILE.exists():
        try:
            return json.loads(PROFIT_TARGETS_FILE.read_text())
        except Exception as e:
            logger.warning(f"Failed to load profit targets: {e}")
    return {}


def _save_profit_targets(data: dict):
    """Save profit targets state to disk."""
    try:
        PROFIT_TARGETS_FILE.write_text(json.dumps(data, indent=2, default=str))
    except Exception as e:
        logger.error(f"Failed to save profit targets: {e}")


def _get_beta(ticker: str) -> Optional[float]:
    """Fetch beta from yfinance."""
    try:
        info = yf.Ticker(ticker).info
        beta = info.get("beta")
        if beta is not None:
            return float(beta)
    except Exception as e:
        logger.warning(f"Failed to fetch beta for {ticker}: {e}")
    return None


def _get_tiers_for_beta(beta: Optional[float]) -> dict:
    """Get tier thresholds based on stock beta."""
    if beta is None:
        return DEFAULT_TIERS
    
    if beta > HIGH_BETA_THRESHOLD:
        return HIGH_BETA_TIERS
    elif beta < LOW_BETA_THRESHOLD:
        return LOW_BETA_TIERS
    else:
        return DEFAULT_TIERS


def _get_current_price(ticker: str) -> Optional[float]:
    """Fetch current price from yfinance."""
    try:
        info = yf.Ticker(ticker).info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price:
            return float(price)
    except Exception as e:
        logger.warning(f"Failed to fetch price for {ticker}: {e}")
    return None


def initialize_profit_targets(holdings: Dict[str, dict]):
    """Initialize profit_targets.json from current holdings if it doesn't exist.
    
    Special handling: CF already had a partial sell at +40%, mark tier 1 as triggered.
    """
    targets = _load_profit_targets()
    
    updated = False
    for ticker, pos in holdings.items():
        if ticker not in targets:
            entry_price = pos.get("entry_price")
            if entry_price:
                targets[ticker] = {
                    "entry_price": entry_price,
                    "tiers_triggered": [],
                }
                
                # Special case: CF already took profit at +40%, mark tier 1 as triggered
                if ticker == "CF":
                    targets[ticker]["tiers_triggered"] = [1]
                    targets[ticker]["tier1_date"] = "2026-03-12"
                    targets[ticker]["tier1_price"] = 135.29  # Approximate price at +40%
                    logger.info(f"CF: Initialized with tier 1 already triggered (partial sell at +40%)")
                
                updated = True
    
    if updated:
        _save_profit_targets(targets)
        logger.info(f"Initialized profit targets for {len(holdings)} holdings")


def check_profit_status(holdings: Dict[str, dict]) -> List[dict]:
    """Check profit-taking status for all holdings.
    
    Returns list of profit alerts with:
    - Current gain %
    - Next tier target
    - Distance to next tier
    - Days held
    - Recommendation: "TAKE_PROFIT", "APPROACHING", "HOLD"
    """
    if not holdings:
        return []
    
    # Initialize if needed
    initialize_profit_targets(holdings)
    
    targets = _load_profit_targets()
    alerts = []
    updated = False
    
    for ticker, pos in holdings.items():
        entry_price = pos.get("entry_price", 0)
        entry_date = pos.get("entry_date")
        shares = pos.get("shares", 0)
        
        if not entry_price or entry_price <= 0:
            continue
        
        # Fetch current data
        current_price = _get_current_price(ticker)
        if current_price is None:
            continue
        
        beta = _get_beta(ticker)
        tiers = _get_tiers_for_beta(beta)
        
        # Calculate gain
        gain_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Get target state
        target_state = targets.get(ticker, {})
        tiers_triggered = target_state.get("tiers_triggered", [])
        
        # Determine next tier
        next_tier = None
        next_tier_pct = None
        
        if 1 not in tiers_triggered:
            next_tier = 1
            next_tier_pct = tiers["tier1"]
        elif 2 not in tiers_triggered:
            next_tier = 2
            next_tier_pct = tiers["tier2"]
        elif 3 not in tiers_triggered:
            next_tier = 3
            next_tier_pct = tiers["tier3"]
        
        # Calculate days held
        days_held = None
        if entry_date:
            try:
                entry_dt = datetime.strptime(entry_date, "%Y-%m-%d")
                days_held = (datetime.now() - entry_dt).days
            except Exception:
                pass
        
        # Build alert
        alert = {
            "ticker": ticker,
            "entry_price": entry_price,
            "current_price": round(current_price, 2),
            "gain_pct": round(gain_pct, 2),
            "shares": shares,
            "beta": round(beta, 2) if beta is not None else None,
            "tier_thresholds": {
                "tier1": tiers["tier1"],
                "tier2": tiers["tier2"],
                "tier3": tiers["tier3"],
            },
            "tiers_triggered": tiers_triggered,
            "next_tier": next_tier,
            "next_tier_pct": next_tier_pct,
            "days_held": days_held,
        }
        
        # Determine recommendation and status
        if next_tier is None:
            # All tiers triggered
            alert["status"] = "ALL_TIERS_COMPLETE"
            alert["recommendation"] = "HOLD"
            alert["message"] = f"✅ {ticker} — All profit tiers taken. Let trailing stop handle remainder."
        
        elif gain_pct >= next_tier_pct:
            # Tier triggered!
            alert["status"] = "TAKE_PROFIT"
            alert["recommendation"] = "TAKE_PROFIT"
            
            # Calculate sell amount
            if next_tier in [1, 2]:
                sell_fraction = 1/3
                sell_shares = round(shares / 3, 6)
            else:  # tier 3
                sell_fraction = 1.0
                sell_shares = shares
            
            alert["sell_shares"] = sell_shares
            alert["sell_fraction"] = sell_fraction
            alert["urgency"] = "HIGH"
            alert["message"] = (
                f"🎯 {ticker} HIT TIER {next_tier} TARGET! "
                f"Gain: {gain_pct:+.1f}% (${entry_price:.2f} → ${current_price:.2f}). "
                f"SELL {sell_fraction:.1%} ({sell_shares:.2f} shares)!"
            )
            
            # Update state
            if ticker not in targets:
                targets[ticker] = {
                    "entry_price": entry_price,
                    "tiers_triggered": [],
                }
            
            if next_tier not in targets[ticker]["tiers_triggered"]:
                targets[ticker]["tiers_triggered"].append(next_tier)
                targets[ticker]["tiers_triggered"].sort()
                targets[ticker][f"tier{next_tier}_date"] = datetime.now().strftime("%Y-%m-%d")
                targets[ticker][f"tier{next_tier}_price"] = round(current_price, 2)
                updated = True
                logger.info(f"{ticker} triggered tier {next_tier} at ${current_price:.2f} ({gain_pct:+.1f}%)")
        
        else:
            # Not yet at next tier
            distance_to_tier = next_tier_pct - gain_pct
            alert["distance_to_next_pct"] = round(distance_to_tier, 2)
            
            if distance_to_tier <= APPROACHING_THRESHOLD:
                alert["status"] = "APPROACHING"
                alert["recommendation"] = "APPROACHING"
                alert["urgency"] = "MEDIUM"
                alert["message"] = (
                    f"🟡 {ticker} approaching tier {next_tier} target ({next_tier_pct:+.0f}%). "
                    f"Current: {gain_pct:+.1f}%, {distance_to_tier:.1f}% away."
                )
            else:
                alert["status"] = "HOLD"
                alert["recommendation"] = "HOLD"
                alert["urgency"] = "NONE"
                alert["message"] = (
                    f"📊 {ticker}: {gain_pct:+.1f}% gain. "
                    f"Next target: tier {next_tier} at {next_tier_pct:+.0f}% ({distance_to_tier:.1f}% away)."
                )
        
        alerts.append(alert)
    
    # Save updated state
    if updated:
        _save_profit_targets(targets)
    
    # Sort: TAKE_PROFIT first, then APPROACHING, then by gain descending
    priority_order = {"TAKE_PROFIT": 0, "APPROACHING": 1, "HOLD": 2, "ALL_TIERS_COMPLETE": 3}
    alerts.sort(key=lambda x: (priority_order.get(x["status"], 99), -x["gain_pct"]))
    
    return alerts


def get_profit_status_single(ticker: str, holdings: Dict[str, dict]) -> Optional[dict]:
    """Get profit-taking status for a single ticker."""
    if ticker not in holdings:
        return None
    
    # Run check for all holdings (to ensure consistency) but filter to one
    all_alerts = check_profit_status(holdings)
    
    for alert in all_alerts:
        if alert["ticker"] == ticker:
            return alert
    
    return None


def get_profit_summary(alerts: List[dict]) -> dict:
    """Generate a summary of profit-taking alerts."""
    if not alerts:
        return {
            "total_positions": 0,
            "take_profit_count": 0,
            "approaching_count": 0,
            "completed_count": 0,
            "total_unrealized_gain_pct": 0,
        }
    
    take_profit = [a for a in alerts if a.get("status") == "TAKE_PROFIT"]
    approaching = [a for a in alerts if a.get("status") == "APPROACHING"]
    completed = [a for a in alerts if a.get("status") == "ALL_TIERS_COMPLETE"]
    
    total_gain = sum(a["gain_pct"] for a in alerts)
    avg_gain = total_gain / len(alerts) if alerts else 0
    
    return {
        "total_positions": len(alerts),
        "take_profit_count": len(take_profit),
        "approaching_count": len(approaching),
        "completed_count": len(completed),
        "avg_gain_pct": round(avg_gain, 2),
        "total_unrealized_gain_pct": round(total_gain, 2),
        "take_profit_tickers": [a["ticker"] for a in take_profit],
        "approaching_tickers": [a["ticker"] for a in approaching],
    }
