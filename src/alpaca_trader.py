"""Alpaca Paper Trading integration for stock-picker.

Connects to Alpaca's paper trading API to execute trades based on scan results.
Works in dry-run mode if API keys are not configured.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HOLDINGS_FILE = DATA_DIR / "holdings.json"

ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
ALPACA_DATA_URL = "https://data.alpaca.markets"
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")


def _is_configured() -> bool:
    return bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)


def _headers() -> Dict[str, str]:
    return {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        "Content-Type": "application/json",
    }


def _dry_run_response(action: str, **kwargs) -> Dict[str, Any]:
    return {
        "dry_run": True,
        "message": f"Alpaca API keys not configured. '{action}' skipped.",
        "timestamp": datetime.now().isoformat(),
        **kwargs,
    }


def get_account() -> Dict[str, Any]:
    """Get paper trading account info."""
    if not _is_configured():
        return _dry_run_response("get_account", account={
            "buying_power": "0.00",
            "portfolio_value": "0.00",
            "cash": "0.00",
            "status": "NOT_CONFIGURED",
        })
    resp = requests.get(f"{ALPACA_BASE_URL}/v2/account", headers=_headers(), timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return {
        "buying_power": data.get("buying_power"),
        "portfolio_value": data.get("portfolio_value"),
        "cash": data.get("cash"),
        "equity": data.get("equity"),
        "status": data.get("status"),
        "currency": data.get("currency"),
        "account_number": data.get("account_number"),
    }


def get_positions() -> List[Dict[str, Any]]:
    """Get current paper positions."""
    if not _is_configured():
        return _dry_run_response("get_positions", positions=[])
    resp = requests.get(f"{ALPACA_BASE_URL}/v2/positions", headers=_headers(), timeout=10)
    resp.raise_for_status()
    return [{
        "ticker": p["symbol"],
        "qty": p["qty"],
        "avg_entry": p["avg_entry_price"],
        "current_price": p["current_price"],
        "market_value": p["market_value"],
        "unrealized_pl": p["unrealized_pl"],
        "unrealized_plpc": p["unrealized_plpc"],
    } for p in resp.json()]


def place_order(ticker: str, qty: float, side: str = "buy", order_type: str = "market",
                time_in_force: str = "day", limit_price: Optional[float] = None) -> Dict[str, Any]:
    """Place a paper trade order."""
    if not _is_configured():
        return _dry_run_response("place_order", order={
            "ticker": ticker, "qty": qty, "side": side, "type": order_type,
        })
    payload = {
        "symbol": ticker,
        "qty": str(qty),
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force,
    }
    if limit_price and order_type == "limit":
        payload["limit_price"] = str(limit_price)

    resp = requests.post(f"{ALPACA_BASE_URL}/v2/orders", headers=_headers(),
                         json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return {
        "id": data["id"],
        "ticker": data["symbol"],
        "qty": data["qty"],
        "side": data["side"],
        "type": data["type"],
        "status": data["status"],
        "submitted_at": data["submitted_at"],
    }


def get_orders(status: str = "all", limit: int = 50) -> List[Dict[str, Any]]:
    """Get paper trading orders."""
    if not _is_configured():
        return _dry_run_response("get_orders", orders=[])
    resp = requests.get(f"{ALPACA_BASE_URL}/v2/orders",
                        headers=_headers(),
                        params={"status": status, "limit": limit},
                        timeout=10)
    resp.raise_for_status()
    return [{
        "id": o["id"],
        "ticker": o["symbol"],
        "qty": o["qty"],
        "side": o["side"],
        "type": o["type"],
        "status": o["status"],
        "filled_avg_price": o.get("filled_avg_price"),
        "submitted_at": o["submitted_at"],
    } for o in resp.json()]


def sync_with_holdings() -> Dict[str, Any]:
    """Sync paper portfolio with our holdings.json.

    Compares current paper positions with holdings.json and returns
    the orders needed to align them. Does NOT auto-execute.
    """
    if not _is_configured():
        # Still show what holdings we have
        holdings = _load_holdings()
        return _dry_run_response("sync_with_holdings",
                                 holdings=holdings,
                                 actions=[],
                                 message="Alpaca not configured. Showing holdings only.")

    holdings = _load_holdings()
    positions = get_positions()
    pos_map = {p["ticker"]: float(p["qty"]) for p in positions}

    actions = []
    # Buy what's in holdings but not in paper
    for h in holdings:
        ticker = h.get("ticker", h.get("symbol", ""))
        target_qty = float(h.get("shares", h.get("qty", 0)))
        current_qty = pos_map.get(ticker, 0)
        diff = target_qty - current_qty
        if diff > 0:
            actions.append({"action": "buy", "ticker": ticker, "qty": diff})
        elif diff < 0:
            actions.append({"action": "sell", "ticker": ticker, "qty": abs(diff)})

    # Sell paper positions not in holdings
    holding_tickers = {h.get("ticker", h.get("symbol", "")) for h in holdings}
    for ticker, qty in pos_map.items():
        if ticker not in holding_tickers:
            actions.append({"action": "sell", "ticker": ticker, "qty": qty})

    return {
        "synced": True,
        "holdings_count": len(holdings),
        "positions_count": len(positions),
        "actions_needed": actions,
        "message": f"{len(actions)} actions needed to sync" if actions else "Already in sync",
    }


def get_performance() -> Dict[str, Any]:
    """Compare paper trading performance vs signal performance."""
    if not _is_configured():
        return _dry_run_response("get_performance", performance={
            "paper_return": None,
            "signal_return": None,
        })

    account = get_account()
    positions = get_positions()
    total_unrealized = sum(float(p["unrealized_pl"]) for p in positions)
    portfolio_value = float(account.get("portfolio_value", 0))

    return {
        "portfolio_value": portfolio_value,
        "total_unrealized_pl": total_unrealized,
        "position_count": len(positions),
        "positions": positions,
        "timestamp": datetime.now().isoformat(),
    }


def _load_holdings() -> List[Dict]:
    if HOLDINGS_FILE.exists():
        return json.loads(HOLDINGS_FILE.read_text())
    return []
