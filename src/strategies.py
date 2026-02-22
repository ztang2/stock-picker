"""Strategy profiles for stock screening."""

from typing import Dict, List, Optional


STRATEGIES: Dict[str, dict] = {
    "conservative": {
        "name": "Conservative",
        "emoji": "🛡️",
        "description": "Defensive, capital preservation. Prefers low volatility, high margins, strong balance sheets.",
        "weights": {
            "fundamentals": 0.40,
            "valuation": 0.25,
            "technicals": 0.08,
            "risk": 0.13,
            "growth": 0.00,
            "sentiment": 0.04,
            "sector_relative": 0.10,
            # sum = 1.00
        },
        "filters": {
            "min_market_cap": 10e9,
            "max_beta": 1.0,
            "min_dividend_yield": 0.01,
        },
        "momentum_bonus": {
            "enabled": False,
            "strong": 0,
            "moderate": 0,
            "weak": 0,
        },
        "smart_money_bonus": {
            "enabled": True,
            "strong_positive": 3,
            "moderate_positive": 1,
            "strong_negative": -3,
            "moderate_negative": -1,
        },
    },
    "balanced": {
        "name": "Balanced",
        "emoji": "⚖️",
        "description": "All-around strategy mixing value and growth. Default for most users.",
        "weights": {
            "fundamentals": 0.26,
            "valuation": 0.17,
            "technicals": 0.22,
            "risk": 0.08,
            "growth": 0.12,
            "sentiment": 0.05,
            "sector_relative": 0.10,
            # sum = 1.00
        },
        "smart_money_bonus": {
            "enabled": True,
            "strong_positive": 5,   # score > 70
            "moderate_positive": 2, # score > 60
            "strong_negative": -5,  # score < 30
            "moderate_negative": -2, # score < 40
        },
        "filters": {
            "min_market_cap": 2e9,
        },
        "momentum_bonus": {
            "enabled": True,
            "strong": 5,
            "moderate": 2,
            "weak": -3,
        },
    },
    "aggressive": {
        "name": "Aggressive",
        "emoji": "🚀",
        "description": "Growth + momentum hunting. High growth, strong momentum, ignores valuation.",
        "weights": {
            "fundamentals": 0.14,
            "valuation": 0.08,
            "technicals": 0.32,
            "risk": 0.04,
            "growth": 0.30,
            "sentiment": 0.02,
            "sector_relative": 0.10,
            # sum = 1.00
        },
        "filters": {
            "min_market_cap": 1e9,
            "min_revenue_growth": 0.10,
        },
        "momentum_bonus": {
            "enabled": True,
            "strong": 8,
            "moderate": 4,
            "weak": -5,
        },
        "smart_money_bonus": {
            "enabled": True,
            "strong_positive": 5,
            "moderate_positive": 2,
            "strong_negative": -5,
            "moderate_negative": -2,
        },
    },
}


def get_strategy(name: str) -> dict:
    """Get strategy config by name. Defaults to 'balanced'."""
    return STRATEGIES.get(name.lower(), STRATEGIES["balanced"])


def list_strategies() -> List[dict]:
    """Return list of all strategies with metadata."""
    result = []
    for key, s in STRATEGIES.items():
        result.append({
            "key": key,
            "name": s["name"],
            "emoji": s["emoji"],
            "description": s["description"],
            "weights": s["weights"],
            "filters": s["filters"],
        })
    return result
