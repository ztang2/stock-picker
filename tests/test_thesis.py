"""Tests for src/thesis.py (template-based thesis only)."""

import pytest


def test_oversold_rsi_appears_in_thesis():
    """RSI < 30 must surface in the generated thesis."""
    from src.thesis import generate_thesis

    stock = {"rsi": 28}
    thesis = generate_thesis(stock)

    assert "RSI 28" in thesis or "oversold" in thesis.lower()


def test_no_signals_returns_fallback():
    """Sparse data returns the fallback string, not a crash."""
    from src.thesis import generate_thesis

    assert generate_thesis({}) == "No standout signals"
    assert generate_thesis({"rsi": 50}) == "No standout signals"


def test_determinism():
    """Same input produces identical output across repeated calls."""
    from src.thesis import generate_thesis

    stock = {
        "rsi": 28,
        "insider_buy_value": 5_000_000,
        "consecutive_days": 7,
        "adx": 35,
    }
    outputs = {generate_thesis(stock) for _ in range(10)}
    assert len(outputs) == 1


def test_top_3_selection():
    """With 5+ notable data points, thesis contains exactly 3 ' + '-joined parts."""
    from src.thesis import generate_thesis

    stock = {
        "rsi": 28,                          # oversold, priority 10
        "insider_buy_value": 5_000_000,     # priority 9
        "adx": 35,                          # priority 6
        "consecutive_days": 7,              # priority 7
        "pe_ratio": 8.0,                    # priority 5
        "revenue_growth": 0.25,             # priority 5
        "sentiment": {"pt_upside_pct": 0.30, "recommendation": "buy", "analyst_count": 10},
    }
    thesis = generate_thesis(stock)
    parts = thesis.split(" + ")

    assert len(parts) == 3


def test_highest_priority_points_win():
    """Highest-priority data points (RSI oversold=10, big insider buy=9) appear in output."""
    from src.thesis import generate_thesis

    stock = {
        "rsi": 28,                          # priority 10
        "insider_buy_value": 5_000_000,     # priority 9
        "pe_ratio": 8.0,                    # priority 5
        "piotroski_score": 8,               # priority 4
    }
    thesis = generate_thesis(stock)

    assert "RSI 28" in thesis or "oversold" in thesis.lower()
    assert "insider" in thesis.lower()


def test_insider_selling_surfaces():
    """Large insider selling above the $1M threshold appears in the thesis."""
    from src.thesis import generate_thesis

    stock = {"insider_sell_value": 2_000_000}
    thesis = generate_thesis(stock)

    assert "selling" in thesis.lower()


def test_gemini_not_required(monkeypatch):
    """generate_thesis must work without GEMINI_API_KEY in environment."""
    from src.thesis import generate_thesis

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    thesis = generate_thesis({"rsi": 28})

    assert thesis  # non-empty
