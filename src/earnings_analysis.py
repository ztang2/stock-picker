"""Deep earnings analysis — quarterly trends, beat/miss history, and growth trends."""

import logging
from typing import Dict, List, Optional

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)


def analyze_earnings(ticker: str) -> dict:
    """Deep earnings analysis for a ticker.

    Tracks quarterly trends (revenue growth, margin, EPS), beat/miss history,
    and estimates vs actuals.
    """
    ticker = ticker.upper()

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        return {"ticker": ticker, "error": f"Failed to fetch data: {e}"}

    result = {
        "ticker": ticker,
        "company_name": info.get("shortName", ticker),
    }

    # --- Quarterly earnings (beat/miss history) ---
    try:
        earnings_hist = t.earnings_history
        if earnings_hist is not None and not earnings_hist.empty:
            beats = []
            for _, row in earnings_hist.iterrows():
                eps_est = row.get("epsEstimate")
                eps_act = row.get("epsActual")
                surprise = row.get("surprisePercent") or row.get("surprise(%)")
                
                entry = {
                    "quarter": str(row.get("quarter", "")),
                    "eps_estimate": round(float(eps_est), 3) if pd.notna(eps_est) else None,
                    "eps_actual": round(float(eps_act), 3) if pd.notna(eps_act) else None,
                    "surprise_pct": round(float(surprise), 2) if pd.notna(surprise) else None,
                }
                
                if pd.notna(eps_est) and pd.notna(eps_act):
                    entry["beat"] = float(eps_act) > float(eps_est)
                
                beats.append(entry)
            
            result["beat_miss_history"] = beats
            beat_count = sum(1 for b in beats if b.get("beat") is True)
            miss_count = sum(1 for b in beats if b.get("beat") is False)
            total = beat_count + miss_count
            result["beat_rate"] = round(beat_count / total * 100, 1) if total > 0 else None
            result["beat_count"] = beat_count
            result["miss_count"] = miss_count
    except Exception as e:
        logger.warning("Failed to get earnings history for %s: %s", ticker, e)

    # --- Quarterly financials for trend analysis ---
    try:
        q_financials = t.quarterly_financials
        if q_financials is not None and not q_financials.empty:
            quarters = []
            for col in q_financials.columns[:8]:  # Last 8 quarters
                q_data = {"period": str(col.date()) if hasattr(col, 'date') else str(col)}
                
                revenue = q_financials.loc["Total Revenue", col] if "Total Revenue" in q_financials.index else None
                net_income = q_financials.loc["Net Income", col] if "Net Income" in q_financials.index else None
                gross_profit = q_financials.loc["Gross Profit", col] if "Gross Profit" in q_financials.index else None
                
                if pd.notna(revenue):
                    q_data["revenue"] = float(revenue)
                if pd.notna(net_income):
                    q_data["net_income"] = float(net_income)
                if pd.notna(gross_profit) and pd.notna(revenue) and revenue > 0:
                    q_data["gross_margin"] = round(float(gross_profit) / float(revenue) * 100, 2)
                if pd.notna(net_income) and pd.notna(revenue) and revenue > 0:
                    q_data["net_margin"] = round(float(net_income) / float(revenue) * 100, 2)
                
                quarters.append(q_data)
            
            result["quarterly_data"] = quarters
            
            # Compute trends
            revenues = [q["revenue"] for q in quarters if "revenue" in q]
            margins = [q["net_margin"] for q in quarters if "net_margin" in q]
            
            if len(revenues) >= 2:
                # YoY revenue growth (compare Q vs Q-4 if available, else sequential)
                if len(revenues) >= 5:
                    yoy_growths = []
                    for i in range(min(4, len(revenues) - 4)):
                        if revenues[i + 4] > 0:
                            yoy_growths.append((revenues[i] - revenues[i + 4]) / abs(revenues[i + 4]) * 100)
                    if yoy_growths:
                        result["revenue_growth_trend"] = {
                            "latest_yoy": round(yoy_growths[0], 2) if yoy_growths else None,
                            "avg_yoy": round(sum(yoy_growths) / len(yoy_growths), 2),
                            "trend": "improving" if len(yoy_growths) >= 2 and yoy_growths[0] > yoy_growths[-1] else "declining",
                        }
                
                # Sequential growth
                seq_growths = []
                for i in range(len(revenues) - 1):
                    if revenues[i + 1] > 0:
                        seq_growths.append((revenues[i] - revenues[i + 1]) / abs(revenues[i + 1]) * 100)
                if seq_growths:
                    result["sequential_revenue_growth"] = [round(g, 2) for g in seq_growths[:4]]
            
            if len(margins) >= 2:
                result["margin_trend"] = {
                    "latest": margins[0],
                    "previous": margins[1],
                    "trend": "expanding" if margins[0] > margins[1] else "contracting",
                    "values": margins[:4],
                }
    except Exception as e:
        logger.warning("Failed to get quarterly financials for %s: %s", ticker, e)

    # --- EPS trend ---
    try:
        q_earnings = t.quarterly_earnings
        if q_earnings is not None and not q_earnings.empty:
            eps_values = []
            for idx, row in q_earnings.iterrows():
                earnings = row.get("Earnings")
                if pd.notna(earnings):
                    eps_values.append({"quarter": str(idx), "earnings": float(earnings)})
            
            if len(eps_values) >= 2:
                result["eps_trend"] = {
                    "values": eps_values[:8],
                    "trend": "improving" if eps_values[0]["earnings"] > eps_values[-1]["earnings"] else "declining",
                }
    except Exception as e:
        logger.warning("Failed to get EPS trend for %s: %s", ticker, e)

    # --- Analyst estimates ---
    try:
        result["analyst_estimates"] = {
            "forward_eps": info.get("forwardEps"),
            "trailing_eps": info.get("trailingEps"),
            "earnings_growth": info.get("earningsGrowth"),
            "revenue_growth": info.get("revenueGrowth"),
            "target_mean_price": info.get("targetMeanPrice"),
            "recommendation": info.get("recommendationKey"),
            "num_analysts": info.get("numberOfAnalystOpinions"),
        }
    except Exception:
        pass

    # --- Overall assessment ---
    signals = []
    if result.get("beat_rate") is not None:
        if result["beat_rate"] >= 75:
            signals.append("consistent_beater")
        elif result["beat_rate"] <= 25:
            signals.append("consistent_misser")
    
    rgt = result.get("revenue_growth_trend", {})
    if rgt.get("trend") == "improving":
        signals.append("accelerating_growth")
    elif rgt.get("trend") == "declining":
        signals.append("decelerating_growth")
    
    mt = result.get("margin_trend", {})
    if mt.get("trend") == "expanding":
        signals.append("margin_expansion")
    elif mt.get("trend") == "contracting":
        signals.append("margin_compression")

    result["signals"] = signals
    
    # Score 0-100
    score = 50
    if result.get("beat_rate") is not None:
        score += (result["beat_rate"] - 50) * 0.3
    if "accelerating_growth" in signals:
        score += 10
    elif "decelerating_growth" in signals:
        score -= 10
    if "margin_expansion" in signals:
        score += 10
    elif "margin_compression" in signals:
        score -= 10
    
    result["earnings_quality_score"] = round(max(0, min(100, score)), 1)

    return result
