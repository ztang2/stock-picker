"""Tests for src/insider.py smart money signals."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest


def _mock_ticker_with_upgrades(upgrades: int, downgrades: int, pt_raises: int = 0):
    """Build a MagicMock yfinance.Ticker with given recent analyst actions."""
    ticker = MagicMock()
    now = datetime.now()

    rows = []
    for _ in range(upgrades):
        rows.append({"Action": "up", "currentPriceTarget": 150, "priorPriceTarget": 140 if pt_raises > 0 else 150})
    for _ in range(downgrades):
        rows.append({"Action": "down", "currentPriceTarget": 150, "priorPriceTarget": 150})

    if rows:
        df = pd.DataFrame(rows, index=[now - timedelta(days=5)] * len(rows))
        ticker.upgrades_downgrades = df
    else:
        ticker.upgrades_downgrades = None

    ticker.recommendations_summary = None
    return ticker


def _mock_ticker_with_insider_summary(buy_count: int, sell_count: int, net_shares: int, pct: float = 0.0):
    """Build a MagicMock with insider_purchases summary table rows."""
    ticker = MagicMock()
    df = pd.DataFrame([
        ["Purchases", buy_count],
        ["Sales", sell_count],
        ["Net Shares Purchased", net_shares],
        ["% Net Shares Purchased", pct],
    ])
    # Real code does `row.iloc[0]` (label) and `row.iloc[1]` (value), positional.
    ticker.insider_purchases = df
    ticker.insider_transactions = None
    return ticker


def test_positive_revisions_raise_score():
    """Heavy upgrades push analyst score above neutral (50)."""
    from src.insider import analyze_analyst_signals

    ticker = _mock_ticker_with_upgrades(upgrades=4, downgrades=0)
    result = analyze_analyst_signals(ticker)

    assert result["score"] > 50
    assert result["upgrades_30d"] == 4
    assert result["downgrades_30d"] == 0


def test_negative_revisions_lower_score():
    """Heavy downgrades push analyst score below neutral."""
    from src.insider import analyze_analyst_signals

    ticker = _mock_ticker_with_upgrades(upgrades=0, downgrades=4)
    result = analyze_analyst_signals(ticker)

    assert result["score"] < 50
    assert result["downgrades_30d"] == 4


def test_no_analyst_data_returns_neutral():
    """A ticker with no analyst data scores neutral (50), not a crash."""
    from src.insider import analyze_analyst_signals

    ticker = MagicMock()
    ticker.upgrades_downgrades = None
    ticker.recommendations_summary = None

    result = analyze_analyst_signals(ticker)

    assert result["score"] == 50
    assert result["upgrades_30d"] == 0


def test_insider_buying_raises_score():
    """Net insider buying with more buys than sells raises the score."""
    from src.insider import analyze_insider_signals

    ticker = _mock_ticker_with_insider_summary(buy_count=6, sell_count=1, net_shares=50_000)
    result = analyze_insider_signals(ticker)

    assert result["score"] > 50
    assert result["buy_count"] == 6
    assert result["sell_count"] == 1


def test_heavy_insider_selling_lowers_score():
    """Lopsided insider selling (sells > 3x buys) lowers the score."""
    from src.insider import analyze_insider_signals

    ticker = _mock_ticker_with_insider_summary(buy_count=1, sell_count=10, net_shares=-100_000)
    result = analyze_insider_signals(ticker)

    assert result["score"] < 50


def test_no_insider_data_returns_neutral():
    """Missing insider data does not crash and returns neutral score."""
    from src.insider import analyze_insider_signals

    ticker = MagicMock()
    ticker.insider_purchases = None
    ticker.insider_transactions = None

    result = analyze_insider_signals(ticker)

    assert result["score"] == 50


def test_combined_score_weights_analyst_60_insider_40():
    """Combined score = 0.6 * analyst + 0.4 * insider (documented weighting)."""
    from src.insider import get_combined_smart_money_score

    ticker = MagicMock()
    ticker.upgrades_downgrades = None
    ticker.recommendations_summary = None
    ticker.insider_purchases = None
    ticker.insider_transactions = None

    result = get_combined_smart_money_score(ticker)

    expected = result["analyst_score"] * 0.6 + result["insider_score"] * 0.4
    assert abs(result["score"] - round(expected, 1)) < 0.01


def test_combined_score_bounded_0_to_100():
    """Combined score never leaves the [0, 100] range regardless of inputs."""
    from src.insider import get_combined_smart_money_score

    ticker = _mock_ticker_with_insider_summary(buy_count=20, sell_count=0, net_shares=1_000_000, pct=0.05)
    rows = [{"Action": "up", "currentPriceTarget": 200, "priorPriceTarget": 150} for _ in range(10)]
    ticker.upgrades_downgrades = pd.DataFrame(rows, index=[datetime.now() - timedelta(days=5)] * 10)
    ticker.recommendations_summary = None

    result = get_combined_smart_money_score(ticker)

    assert 0 <= result["score"] <= 100
