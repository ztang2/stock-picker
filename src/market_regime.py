"""Market regime detection based on multi-signal macro analysis.

Signals (7 total):
1. SPY vs 200MA (trend)
2. SPY vs 50MA (momentum)
3. SPY RSI (overbought/oversold)
4. VIX level (fear gauge)
5. US 10Y Treasury yield trend (rate environment)
6. US Dollar Index DXY trend (dollar strength)
7. Oil price trend (commodity/inflation pressure)

Regime: bull / bear / sideways with confidence score.
"""

import logging
from typing import Optional, Dict

import numpy as np
import pandas as pd
import yfinance as yf

from .indicators import _rsi

logger = logging.getLogger(__name__)

# Macro tickers
MACRO_TICKERS = {
    "vix": "^VIX",
    "us10y": "^TNX",      # 10-Year Treasury Yield
    "dxy": "DX-Y.NYB",    # US Dollar Index
    "oil": "CL=F",        # WTI Crude Oil Futures
}


def _ma_slope(series: pd.Series, period: int, lookback: int = 20) -> Optional[float]:
    """Calculate the slope of a moving average over lookback periods."""
    if series is None or len(series) < period + lookback:
        return None
    ma = series.rolling(period).mean()
    if len(ma) < lookback:
        return None
    ma_prev = ma.iloc[-(lookback + 1)]
    ma_curr = ma.iloc[-1]
    if pd.isna(ma_prev) or pd.isna(ma_curr) or ma_prev == 0:
        return None
    pct_change = ((ma_curr - ma_prev) / ma_prev) * 100
    return float(pct_change / lookback)


def _fetch_macro_data() -> Dict[str, dict]:
    """Fetch macro indicator data (VIX, 10Y, DXY, Oil)."""
    results = {}
    for name, ticker in MACRO_TICKERS.items():
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="6mo")
            if hist is None or len(hist) < 20:
                logger.warning(f"Insufficient data for {name} ({ticker})")
                continue

            close = hist["Close"]
            current = float(close.iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
            ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None

            # 20-day change
            if len(close) >= 21:
                prev_20d = float(close.iloc[-21])
                change_20d_pct = ((current - prev_20d) / prev_20d) * 100
            else:
                change_20d_pct = 0

            # 5-day change (short-term momentum)
            if len(close) >= 6:
                prev_5d = float(close.iloc[-6])
                change_5d_pct = ((current - prev_5d) / prev_5d) * 100
            else:
                change_5d_pct = 0

            results[name] = {
                "current": round(current, 2),
                "ma20": round(ma20, 2) if ma20 and not pd.isna(ma20) else None,
                "ma50": round(ma50, 2) if ma50 and not pd.isna(ma50) else None,
                "change_20d_pct": round(change_20d_pct, 2),
                "change_5d_pct": round(change_5d_pct, 2),
            }
        except Exception as e:
            logger.warning(f"Failed to fetch {name}: {e}")

    return results


def _score_vix(vix_data: dict) -> Dict:
    """Score VIX signal.

    VIX < 15: Low fear (bullish)
    VIX 15-20: Normal
    VIX 20-30: Elevated fear (cautious)
    VIX > 30: High fear (bearish)
    VIX > 40: Extreme fear (potential capitulation → contrarian bullish)
    """
    current = vix_data["current"]
    change_5d = vix_data["change_5d_pct"]

    if current > 40:
        # Extreme fear — potential capitulation, contrarian signal
        signal = "extreme_fear"
        score = -1  # Slightly bearish but watch for reversal
        note = f"VIX {current:.1f} — EXTREME fear, possible capitulation"
    elif current > 30:
        signal = "high_fear"
        score = -2
        note = f"VIX {current:.1f} — HIGH fear"
    elif current > 20:
        signal = "elevated"
        score = -1
        note = f"VIX {current:.1f} — elevated fear"
    elif current > 15:
        signal = "normal"
        score = 0
        note = f"VIX {current:.1f} — normal"
    else:
        signal = "low_fear"
        score = 1
        note = f"VIX {current:.1f} — low fear (complacent)"

    # VIX spike detection (5-day)
    if change_5d > 30:
        score -= 1
        note += f" | SPIKE +{change_5d:.0f}% in 5d"
    elif change_5d < -20:
        score += 1
        note += f" | rapid decline {change_5d:.0f}% in 5d"

    return {"signal": signal, "score": score, "note": note}


def _score_yields(yield_data: dict) -> Dict:
    """Score Treasury yield signal.

    Rising yields: pressure on growth/tech stocks
    Falling yields: flight to safety OR rate cut expectations (bullish for stocks)
    Very high yields (>5%): restrictive, bearish for equities
    """
    current = yield_data["current"]
    change_20d = yield_data["change_20d_pct"]

    if current > 5.0:
        score = -2
        note = f"10Y {current:.2f}% — restrictive territory"
    elif current > 4.5:
        score = -1
        note = f"10Y {current:.2f}% — elevated"
    elif current < 3.5:
        score = 1
        note = f"10Y {current:.2f}% — accommodative"
    else:
        score = 0
        note = f"10Y {current:.2f}% — neutral"

    # Trend matters more than level
    if change_20d > 5:
        score -= 1
        note += f" | rising fast (+{change_20d:.1f}% in 20d)"
    elif change_20d < -5:
        score += 1
        note += f" | falling ({change_20d:.1f}% in 20d)"

    signal = "rising" if change_20d > 2 else "falling" if change_20d < -2 else "stable"
    return {"signal": signal, "score": score, "note": note}


def _score_dxy(dxy_data: dict) -> Dict:
    """Score Dollar Index signal.

    Strong dollar: headwind for US multinationals, bearish for commodities
    Weak dollar: tailwind for exports, bullish for commodities/EM
    """
    current = dxy_data["current"]
    change_20d = dxy_data["change_20d_pct"]

    if change_20d > 3:
        score = -1
        signal = "strengthening"
        note = f"DXY {current:.1f} — strengthening (+{change_20d:.1f}% in 20d)"
    elif change_20d < -3:
        score = 1
        signal = "weakening"
        note = f"DXY {current:.1f} — weakening ({change_20d:.1f}% in 20d)"
    else:
        score = 0
        signal = "stable"
        note = f"DXY {current:.1f} — stable ({change_20d:+.1f}% in 20d)"

    return {"signal": signal, "score": score, "note": note}


def _score_oil(oil_data: dict) -> Dict:
    """Score Oil price signal.

    Rising oil: inflation pressure, good for energy, bad for consumers
    Falling oil: deflationary, good for consumers, bad for energy
    Spike > 20% in 20d: supply shock (geopolitical risk)
    """
    current = oil_data["current"]
    change_20d = oil_data["change_20d_pct"]
    change_5d = oil_data["change_5d_pct"]

    score = 0
    if change_20d > 20:
        score = -2
        signal = "spike"
        note = f"Oil ${current:.1f} — SUPPLY SHOCK (+{change_20d:.0f}% in 20d)"
    elif change_20d > 10:
        score = -1
        signal = "rising"
        note = f"Oil ${current:.1f} — rising fast (+{change_20d:.1f}% in 20d)"
    elif change_20d < -10:
        score = 1
        signal = "falling"
        note = f"Oil ${current:.1f} — falling ({change_20d:.1f}% in 20d)"
    else:
        signal = "stable"
        note = f"Oil ${current:.1f} — stable ({change_20d:+.1f}% in 20d)"

    # Acute spike detection
    if change_5d > 15:
        score -= 1
        note += " | ACUTE spike in 5d"

    return {"signal": signal, "score": score, "note": note}


def detect_market_regime(spy_hist: pd.DataFrame) -> Dict:
    """Detect current market regime based on 7 macro signals.

    Returns dict with regime, all indicator data, individual signal scores,
    composite score, confidence, and description.
    """
    result = {
        "regime": "sideways",
        "spy_price": None,
        "spy_ma200": None,
        "spy_ma50": None,
        "spy_rsi": None,
        "ma200_slope": None,
        "ma50_slope": None,
        "confidence": 0.5,
        "description": "Insufficient data for regime detection",
        "signals": {},
        "macro": {},
        "signal_scores": {},
        "composite_score": 0,
    }

    if spy_hist is None or len(spy_hist) < 200:
        logger.warning("Insufficient SPY data for regime detection")
        return result

    try:
        close = spy_hist["Close"]
        current_price = float(close.iloc[-1])

        # Calculate SPY indicators
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])

        if pd.isna(ma50) or pd.isna(ma200):
            return result

        rsi = _rsi(close)
        ma200_slope = _ma_slope(close, 200, lookback=20)
        ma50_slope = _ma_slope(close, 50, lookback=20)

        distance_200ma_pct = ((current_price - ma200) / ma200) * 100
        distance_50ma_pct = ((current_price - ma50) / ma50) * 100

        # === Signal 1: SPY vs 200MA (trend) ===
        spy_trend_score = 0
        if current_price > ma200:
            spy_trend_score += 1
            if ma200_slope and ma200_slope > 0.01:
                spy_trend_score += 1
        else:
            spy_trend_score -= 1
            if ma200_slope and ma200_slope < -0.01:
                spy_trend_score -= 1

        # === Signal 2: SPY vs 50MA (momentum) ===
        spy_momentum_score = 0
        if current_price > ma50:
            spy_momentum_score = 1
        elif current_price < ma50:
            spy_momentum_score = -1

        # === Signal 3: SPY RSI ===
        rsi_score = 0
        if rsi is not None:
            if rsi > 70:
                rsi_score = -1  # Overbought
            elif rsi > 50:
                rsi_score = 1   # Bullish
            elif rsi > 30:
                rsi_score = -1  # Bearish
            else:
                rsi_score = 0   # Oversold — potential reversal

        # === Signals 4-7: Macro indicators ===
        macro_data = _fetch_macro_data()
        vix_signal = _score_vix(macro_data["vix"]) if "vix" in macro_data else None
        yield_signal = _score_yields(macro_data["us10y"]) if "us10y" in macro_data else None
        dxy_signal = _score_dxy(macro_data["dxy"]) if "dxy" in macro_data else None
        oil_signal = _score_oil(macro_data["oil"]) if "oil" in macro_data else None

        # === FRED economic data (optional, non-blocking) ===
        fred_summary = None
        try:
            from .fred_data import get_economic_summary
            fred_summary = get_economic_summary()
            if "error" in fred_summary:
                fred_summary = None
        except Exception as e:
            logger.warning(f"FRED data unavailable: {e}")

        # === Composite Score (-14 to +14 range, normalized) ===
        scores = {
            "spy_trend": spy_trend_score,       # -2 to +2
            "spy_momentum": spy_momentum_score,  # -1 to +1
            "spy_rsi": rsi_score,                # -1 to +1
        }
        if vix_signal:
            scores["vix"] = vix_signal["score"]
        if yield_signal:
            scores["us10y"] = yield_signal["score"]
        if dxy_signal:
            scores["dxy"] = dxy_signal["score"]
        if oil_signal:
            scores["oil"] = oil_signal["score"]
        if fred_summary and "composite_score" in fred_summary:
            # Clamp FRED score to ±3 to not overwhelm market signals
            fred_score = max(-3, min(3, fred_summary["composite_score"]))
            scores["fred_economic"] = fred_score

        composite = sum(scores.values())
        max_possible = sum(abs(v) for v in scores.values()) or 1

        # Determine regime from composite
        if composite >= 3:
            regime = "bull"
            confidence = min(0.95, 0.6 + (composite / max_possible) * 0.3)
        elif composite <= -3:
            regime = "bear"
            confidence = min(0.95, 0.6 + (abs(composite) / max_possible) * 0.3)
        else:
            regime = "sideways"
            confidence = 0.5 + (1 - abs(composite) / max_possible) * 0.2

        # Build signals dict (backward compatible)
        signals = {
            "above_ma200": current_price > ma200,
            "above_ma50": current_price > ma50,
            "ma200_slope_positive": ma200_slope is not None and ma200_slope > 0.01,
            "ma200_slope_negative": ma200_slope is not None and ma200_slope < -0.01,
            "ma200_slope_flat": ma200_slope is not None and abs(ma200_slope) <= 0.01,
            "near_ma200": abs(distance_200ma_pct) <= 3.0,
            "rsi_bullish": rsi is not None and rsi > 50,
            "rsi_bearish": rsi is not None and rsi < 50,
        }

        # Description
        n_signals = len(scores)
        parts = [f"SPY ${current_price:.2f} ({distance_200ma_pct:+.1f}% vs 200MA)"]
        parts.append(f"Composite: {composite:+d}/{n_signals} → {regime.upper()}")
        if vix_signal:
            parts.append(vix_signal["note"])
        if yield_signal:
            parts.append(yield_signal["note"])
        if oil_signal:
            parts.append(oil_signal["note"])
        if dxy_signal:
            parts.append(dxy_signal["note"])

        description = " | ".join(parts)

        result = {
            "regime": regime,
            "spy_price": round(current_price, 2),
            "spy_ma200": round(ma200, 2),
            "spy_ma50": round(ma50, 2),
            "spy_rsi": round(rsi, 2) if rsi is not None else None,
            "ma200_slope": round(ma200_slope, 4) if ma200_slope is not None else None,
            "ma50_slope": round(ma50_slope, 4) if ma50_slope is not None else None,
            "distance_200ma_pct": round(distance_200ma_pct, 2),
            "distance_50ma_pct": round(distance_50ma_pct, 2),
            "confidence": round(confidence, 2),
            "description": description,
            "signals": signals,
            "macro": macro_data,
            "signal_scores": scores,
            "composite_score": composite,
            "economic": fred_summary if fred_summary else None,
        }

        logger.info(f"Market regime: {regime.upper()} (composite={composite:+d}, confidence={confidence:.0%})")

    except Exception:
        logger.error("Failed to detect market regime", exc_info=True)

    return result


def get_regime_weight_adjustments(regime: str) -> Dict[str, float]:
    """Get weight adjustment multipliers for a given market regime."""
    if regime == "bull":
        return {
            "fundamentals": 1.0,
            "valuation": 0.95,
            "technicals": 1.05,
            "risk": 0.95,
            "growth": 1.05,
            "sentiment": 1.0,
            "sector_relative": 1.0,
        }
    elif regime == "bear":
        return {
            "fundamentals": 1.0,
            "valuation": 1.05,
            "technicals": 0.95,
            "risk": 1.10,
            "growth": 0.90,
            "sentiment": 1.0,
            "sector_relative": 1.0,
        }
    else:
        return {
            "fundamentals": 1.0,
            "valuation": 1.0,
            "technicals": 1.0,
            "risk": 1.0,
            "growth": 1.0,
            "sentiment": 1.0,
            "sector_relative": 1.0,
        }


def get_regime_sell_adjustments(regime: str) -> Dict:
    """Get sell signal threshold adjustments for a given market regime."""
    if regime == "bull":
        return {
            "rsi_threshold_offset": 5,
            "sell_score_multiplier": 0.80,
        }
    elif regime == "bear":
        return {
            "rsi_threshold_offset": -5,
            "sell_score_multiplier": 1.30,
        }
    else:
        return {
            "rsi_threshold_offset": 0,
            "sell_score_multiplier": 1.0,
        }


# ──────────────────────────────────────────────────────────────
# Geopolitical Event Detection & Industry Impact
# ──────────────────────────────────────────────────────────────

# Event types and their trigger conditions (from regime signals)
# Each event maps industries to score adjustments (+bonus or -penalty)
GEOPOLITICAL_EVENTS = {
    "oil_war": {
        # Triggered when: oil signal <= -2 (oil surge) AND vix signal <= -1
        "trigger": lambda scores: scores.get("oil", 0) <= -2 and scores.get("vix", 0) <= -1,
        "name": "Oil/Energy Crisis (War/Sanctions)",
        "beneficiaries": {
            # Industries that profit from high oil prices
            "Oil & Gas E&P": 5,
            "Oil & Gas Integrated": 4,
            "Oil & Gas Midstream": 4,
            "Oil & Gas Refining & Marketing": 4,
            "Oil & Gas Equipment & Services": 3,
            "Agricultural Inputs": 4,       # CF — fertilizer tied to nat gas
            "Uranium": 3,                   # Alternative energy demand
            "Aerospace & Defense": 3,       # Military spending
            "Thermal Coal": 3,
        },
        "casualties": {
            # Industries hurt by high oil + war uncertainty
            "Airlines": -5,
            "Lodging": -4,                  # Hotels
            "REIT - Hotel & Motel": -4,     # Hotel REITs (HST)
            "Resorts & Casinos": -4,
            "Leisure": -3,
            "Travel Services": -4,
            "Restaurants": -2,
            "Trucking": -3,
            "Auto Manufacturers": -3,
            "Recreational Vehicles": -3,
            "Marine Shipping": -2,          # Hormuz disruption
            "Cruise Lines": -4,
        },
    },
    "trade_war": {
        # Triggered when: dxy signal >= +1 (strong dollar) AND composite <= -2
        "trigger": lambda scores: scores.get("dxy", 0) >= 1 and scores.get("oil", 0) >= 0,
        "name": "Trade War / Tariffs",
        "beneficiaries": {
            "Domestic Manufacturing": 3,
            "Utilities - Regulated Electric": 2,
            "Waste Management": 2,
            "Discount Stores": 2,
        },
        "casualties": {
            "Semiconductors": -3,
            "Consumer Electronics": -3,
            "Auto Parts": -3,
            "Farm Products": -2,
            "Luxury Goods": -2,
        },
    },
    "recession_fear": {
        # Triggered when: composite <= -4 AND us10y signal positive (yields rising or inverted)
        "trigger": lambda scores: (scores.get("spy_trend", 0) + scores.get("spy_momentum", 0)) <= -3,
        "name": "Recession / Market Crash",
        "beneficiaries": {
            "Discount Stores": 3,
            "Utilities - Regulated Electric": 3,
            "Gold": 4,
            "Drug Manufacturers - General": 2,
            "Household & Personal Products": 2,
            "Food Distribution": 2,
        },
        "casualties": {
            "Luxury Goods": -4,
            "Apparel Retail": -3,
            "Residential Construction": -3,
            "Auto Manufacturers": -3,
            "Banks - Regional": -2,
        },
    },
}


def detect_geopolitical_events(regime_data: dict) -> list:
    """Detect active geopolitical events from regime signal scores.
    
    Returns list of active events with their industry adjustments.
    """
    if not regime_data:
        return []

    scores = regime_data.get("signal_scores", {})
    if not scores:
        return []

    active_events = []
    for event_id, event_cfg in GEOPOLITICAL_EVENTS.items():
        try:
            if event_cfg["trigger"](scores):
                active_events.append({
                    "event": event_id,
                    "name": event_cfg["name"],
                    "beneficiaries": event_cfg["beneficiaries"],
                    "casualties": event_cfg["casualties"],
                })
                logger.info(f"Geopolitical event detected: {event_cfg['name']}")
        except Exception:
            pass

    return active_events


def get_geopolitical_adjustments(regime_data: dict) -> dict:
    """Return a dict of {industry: score_adjustment} from all active events.
    
    Multiple events stack additively.
    """
    events = detect_geopolitical_events(regime_data)
    adjustments = {}
    
    for event in events:
        for industry, bonus in event["beneficiaries"].items():
            adjustments[industry] = adjustments.get(industry, 0) + bonus
        for industry, penalty in event["casualties"].items():
            adjustments[industry] = adjustments.get(industry, 0) + penalty

    return adjustments
