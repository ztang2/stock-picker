"""Strategy profiles for stock screening."""

from typing import Dict, List, Optional


STRATEGIES: Dict[str, dict] = {
    "conservative": {
        "name": "Conservative",
        "emoji": "🛡️",
        "description": "Defensive, capital preservation. Prefers low volatility, high margins, strong balance sheets.",
        "weights": {
            "fundamentals": 0.45,
            "valuation": 0.30,
            "technicals": 0.10,
            "risk": 0.15,
            "growth": 0.00,
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
    },
    "balanced": {
        "name": "Balanced",
        "emoji": "⚖️",
        "description": "All-around strategy mixing value and growth. Default for most users.",
        "weights": {
            "fundamentals": 0.30,
            "valuation": 0.20,
            "technicals": 0.25,
            "risk": 0.10,
            "growth": 0.15,
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
            "fundamentals": 0.15,
            "valuation": 0.10,
            "technicals": 0.35,
            "risk": 0.05,
            "growth": 0.35,
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
