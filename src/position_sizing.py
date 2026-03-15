"""Position sizing module: conviction-based capital allocation and rebalance suggestions.

Calculates how much capital to allocate to each stock based on:
- Pipeline composite score
- Entry signal strength (STRONG_BUY > BUY > HOLD)
- ML signal agreement
- Early Momentum score
- Quality scores (Piotroski F-Score)
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
SCAN_RESULTS_FILE = DATA_DIR / "scan_results.json"
HOLDINGS_FILE = DATA_DIR / "holdings.json"


def load_scan_results() -> Dict:
    """Load latest scan results."""
    if not SCAN_RESULTS_FILE.exists():
        return {"all_scores": []}
    try:
        return json.loads(SCAN_RESULTS_FILE.read_text())
    except Exception as e:
        logger.error(f"Failed to load scan results: {e}")
        return {"all_scores": []}


def load_holdings() -> Dict:
    """Load current holdings."""
    if not HOLDINGS_FILE.exists():
        return {"holdings": {}}
    try:
        return json.loads(HOLDINGS_FILE.read_text())
    except Exception as e:
        logger.error(f"Failed to load holdings: {e}")
        return {"holdings": {}}


def calculate_conviction_score(ticker: str, scan_data: Optional[Dict] = None) -> Dict:
    """Calculate conviction score (0-100) for a ticker.
    
    Factors:
    - Composite score from pipeline (0-100): base conviction
    - Entry signal: STRONG_BUY +15, BUY +5, HOLD +0, SELL -10
    - Momentum score: >6 = +10, 4-6 = +5, <4 = 0
    - Piotroski score: ≥7 = +10, 5-6 = +5, ≤4 = -10
    
    Returns dict with conviction score and breakdown.
    """
    if scan_data is None:
        scan_data = load_scan_results()
    
    # Find ticker in scan results
    stock_data = None
    for stock in scan_data.get("all_scores", []):
        if stock.get("ticker") == ticker:
            stock_data = stock
            break
    
    if not stock_data:
        return {
            "ticker": ticker,
            "conviction_score": 0,
            "error": "Ticker not found in scan results",
            "breakdown": {}
        }
    
    # Start with composite score as base
    composite = stock_data.get("composite_score", 50)
    conviction = composite
    breakdown = {"composite_score": round(composite, 2)}
    
    # Entry signal adjustment
    entry_signal = stock_data.get("entry_signal", "HOLD")
    signal_boost = 0
    if entry_signal == "STRONG_BUY":
        signal_boost = 15
    elif entry_signal == "BUY":
        signal_boost = 5
    elif entry_signal == "HOLD":
        signal_boost = 0
    elif entry_signal == "SELL":
        signal_boost = -10
    
    conviction += signal_boost
    breakdown["entry_signal"] = entry_signal
    breakdown["signal_boost"] = signal_boost
    
    # Momentum boost
    momentum = stock_data.get("momentum_score")
    momentum_boost = 0
    if momentum is not None:
        if momentum > 6:
            momentum_boost = 10
        elif momentum >= 4:
            momentum_boost = 5
        breakdown["momentum_score"] = round(momentum, 2)
        breakdown["momentum_boost"] = momentum_boost
        conviction += momentum_boost
    
    # Piotroski quality boost
    piotroski = stock_data.get("piotroski_score")
    quality_boost = 0
    if piotroski is not None:
        if piotroski >= 7:
            quality_boost = 10
        elif piotroski >= 5:
            quality_boost = 5
        elif piotroski <= 4:
            quality_boost = -10
        breakdown["piotroski_score"] = piotroski
        breakdown["quality_boost"] = quality_boost
        conviction += quality_boost
    
    # Clamp to 0-100
    conviction = max(0, min(100, conviction))
    
    return {
        "ticker": ticker,
        "conviction_score": round(conviction, 2),
        "breakdown": breakdown
    }


def calculate_position_size(
    conviction_score: float,
    total_portfolio_value: float,
    num_positions: int
) -> Dict:
    """Calculate recommended position size based on conviction.
    
    Logic:
    - Base allocation = portfolio / num_positions (equal weight)
    - Adjust by conviction:
      - conviction > 80: base × 1.5 (cap at 15%)
      - conviction 60-80: base × 1.2
      - conviction 40-60: base × 1.0 (default)
      - conviction < 40: base × 0.7 (floor at 3%)
    
    Returns dict with dollar amount and percentage.
    """
    if num_positions <= 0:
        return {"error": "num_positions must be > 0"}
    
    if total_portfolio_value <= 0:
        return {"error": "total_portfolio_value must be > 0"}
    
    # Base equal-weight allocation
    base_pct = 100.0 / num_positions
    
    # Conviction multiplier
    if conviction_score > 80:
        multiplier = 1.5
    elif conviction_score >= 60:
        multiplier = 1.2
    elif conviction_score >= 40:
        multiplier = 1.0
    else:
        multiplier = 0.7
    
    # Calculate raw percentage
    raw_pct = base_pct * multiplier
    
    # Apply hard limits: min 3%, max 15%
    final_pct = max(3.0, min(15.0, raw_pct))
    
    # Convert to dollar amount
    dollar_amount = total_portfolio_value * (final_pct / 100)
    
    return {
        "conviction_score": round(conviction_score, 2),
        "base_allocation_pct": round(base_pct, 2),
        "multiplier": multiplier,
        "raw_allocation_pct": round(raw_pct, 2),
        "final_allocation_pct": round(final_pct, 2),
        "dollar_amount": round(dollar_amount, 2)
    }


def get_portfolio_sizing(
    total_portfolio_value: float,
    tickers: Optional[List[str]] = None
) -> Dict:
    """Calculate position sizing for entire portfolio.
    
    If tickers not provided, uses current holdings.
    Returns sizing for each ticker with rebalance suggestions.
    """
    scan_data = load_scan_results()
    holdings_data = load_holdings()
    
    # Use provided tickers or current holdings
    if tickers is None:
        tickers = list(holdings_data.get("holdings", {}).keys())
    
    if not tickers:
        return {"error": "No tickers provided and no current holdings"}
    
    num_positions = len(tickers)
    
    # Calculate conviction and sizing for each ticker
    positions = []
    total_allocated_pct = 0
    
    for ticker in tickers:
        conviction_data = calculate_conviction_score(ticker, scan_data)
        conviction = conviction_data.get("conviction_score", 0)
        
        sizing = calculate_position_size(conviction, total_portfolio_value, num_positions)
        
        position = {
            "ticker": ticker,
            "conviction": conviction_data,
            "sizing": sizing
        }
        
        positions.append(position)
        total_allocated_pct += sizing.get("final_allocation_pct", 0)
    
    # Sort by conviction (highest first)
    positions.sort(key=lambda p: p["conviction"]["conviction_score"], reverse=True)
    
    # Normalize if total > 100%
    if total_allocated_pct > 100:
        scale_factor = 100.0 / total_allocated_pct
        for pos in positions:
            old_pct = pos["sizing"]["final_allocation_pct"]
            new_pct = old_pct * scale_factor
            pos["sizing"]["final_allocation_pct"] = round(new_pct, 2)
            pos["sizing"]["dollar_amount"] = round(total_portfolio_value * (new_pct / 100), 2)
            pos["sizing"]["normalized"] = True
        total_allocated_pct = 100.0
    
    return {
        "total_portfolio_value": total_portfolio_value,
        "num_positions": num_positions,
        "total_allocated_pct": round(total_allocated_pct, 2),
        "positions": positions
    }


def get_rebalance_suggestions(total_portfolio_value: float) -> Dict:
    """Analyze current holdings and suggest rebalancing.
    
    Compares current allocations with recommended allocations based on conviction.
    Respects 30-day minimum hold rule.
    """
    holdings_data = load_holdings()
    holdings = holdings_data.get("holdings", {})
    
    if not holdings:
        return {"error": "No current holdings to analyze"}
    
    # Get current prices and calculate current allocations
    import yfinance as yf
    
    current_positions = []
    total_current_value = 0
    
    for ticker, holding in holdings.items():
        shares = holding.get("shares", 0)
        entry_price = holding.get("entry_price", 0)
        entry_date_str = holding.get("entry_date", "")
        
        # Get current price
        try:
            stock = yf.Ticker(ticker)
            current_price = stock.info.get("currentPrice", stock.info.get("regularMarketPrice", entry_price))
        except Exception as e:
            logger.warning(f"Failed to get price for {ticker}: {e}")
            current_price = entry_price
        
        current_value = shares * current_price
        total_current_value += current_value
        
        # Check if within 30-day hold period
        try:
            entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d")
            days_held = (datetime.now() - entry_date).days
            within_hold_period = days_held < 30
        except Exception:
            within_hold_period = False
            days_held = None
        
        current_positions.append({
            "ticker": ticker,
            "shares": shares,
            "entry_price": entry_price,
            "current_price": round(current_price, 2),
            "current_value": round(current_value, 2),
            "entry_date": entry_date_str,
            "days_held": days_held,
            "within_hold_period": within_hold_period
        })
    
    # Use actual portfolio value if calculated
    if total_current_value > 0:
        portfolio_value = total_current_value
    else:
        portfolio_value = total_portfolio_value
    
    # Calculate current allocation percentages
    for pos in current_positions:
        pos["current_allocation_pct"] = round((pos["current_value"] / portfolio_value) * 100, 2)
    
    # Get recommended sizing
    tickers = [p["ticker"] for p in current_positions]
    recommended = get_portfolio_sizing(portfolio_value, tickers)
    
    # Build rebalance suggestions
    suggestions = []
    
    for current in current_positions:
        ticker = current["ticker"]
        
        # Find recommended allocation
        rec_position = next((p for p in recommended["positions"] if p["ticker"] == ticker), None)
        if not rec_position:
            continue
        
        rec_pct = rec_position["sizing"]["final_allocation_pct"]
        current_pct = current["current_allocation_pct"]
        
        diff_pct = rec_pct - current_pct
        diff_dollars = (diff_pct / 100) * portfolio_value
        
        # Determine action
        action = "HOLD"
        if abs(diff_pct) < 2:  # Within 2% is close enough
            action = "HOLD"
        elif diff_pct > 0:
            action = "INCREASE" if not current["within_hold_period"] else "HOLD (30-day lock)"
        else:
            action = "DECREASE" if not current["within_hold_period"] else "HOLD (30-day lock)"
        
        suggestion = {
            "ticker": ticker,
            "current_allocation_pct": current_pct,
            "current_value": current["current_value"],
            "recommended_allocation_pct": rec_pct,
            "recommended_value": round((rec_pct / 100) * portfolio_value, 2),
            "diff_pct": round(diff_pct, 2),
            "diff_dollars": round(diff_dollars, 2),
            "action": action,
            "conviction_score": rec_position["conviction"]["conviction_score"],
            "days_held": current["days_held"],
            "within_hold_period": current["within_hold_period"]
        }
        
        suggestions.append(suggestion)
    
    # Sort by absolute difference (biggest rebalances first)
    suggestions.sort(key=lambda s: abs(s["diff_pct"]), reverse=True)
    
    return {
        "portfolio_value": round(portfolio_value, 2),
        "num_positions": len(current_positions),
        "rebalance_suggestions": suggestions
    }


def get_single_ticker_sizing(
    ticker: str,
    total_portfolio_value: float,
    num_positions: int
) -> Dict:
    """Get conviction score and recommended sizing for a single ticker.
    
    Useful for evaluating new position candidates.
    """
    conviction_data = calculate_conviction_score(ticker)
    
    if "error" in conviction_data:
        return conviction_data
    
    conviction = conviction_data["conviction_score"]
    sizing = calculate_position_size(conviction, total_portfolio_value, num_positions)
    
    return {
        "ticker": ticker,
        "conviction": conviction_data,
        "sizing": sizing
    }
