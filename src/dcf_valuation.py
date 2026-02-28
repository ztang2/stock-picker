"""Discounted Cash Flow (DCF) valuation model.

Calculates intrinsic value per share using FCF projections, WACC, and terminal value.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import yfinance as yf

logger = logging.getLogger(__name__)

# Default assumptions
DEFAULT_RISK_FREE_RATE = 0.043  # ~10Y Treasury yield
DEFAULT_EQUITY_RISK_PREMIUM = 0.055  # Historical ERP
DEFAULT_TERMINAL_GROWTH = 0.025  # Long-term GDP growth
PROJECTION_YEARS = 5


def _get_fcf_from_yfinance(ticker_obj) -> Optional[float]:
    """Extract trailing FCF from yfinance."""
    try:
        cf = ticker_obj.cashflow
        if cf is not None and not cf.empty:
            ocf = None
            capex = None
            for label in cf.index:
                ll = str(label).lower()
                if "operating" in ll and "cash" in ll:
                    ocf = cf.loc[label].iloc[0]
                if "capital" in ll and "expend" in ll:
                    capex = cf.loc[label].iloc[0]
            if ocf is not None:
                capex = capex if capex is not None else 0
                # capex is typically negative in yfinance
                return float(ocf) + float(capex) if capex < 0 else float(ocf) - abs(float(capex))
    except Exception as e:
        logger.warning("Failed to get FCF: %s", e)
    
    # Fallback: freeCashflow from info
    info = ticker_obj.info or {}
    fcf = info.get("freeCashflow")
    if fcf:
        return float(fcf)
    return None


def _estimate_growth_rate(ticker_obj) -> float:
    """Estimate FCF growth rate from historical data and analyst estimates."""
    info = ticker_obj.info or {}
    
    # Use analyst earnings growth as proxy
    growth = info.get("earningsGrowth")  # next year
    long_term = info.get("earningsQuarterlyGrowth")
    revenue_growth = info.get("revenueGrowth")
    
    estimates = [g for g in [growth, revenue_growth] if g is not None and -1 < g < 2]
    
    if estimates:
        avg = sum(estimates) / len(estimates)
        # Cap between -10% and 30%
        return max(-0.10, min(0.30, avg))
    
    # Fallback: conservative 5%
    return 0.05


def calculate_wacc(
    ticker_obj,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    equity_risk_premium: float = DEFAULT_EQUITY_RISK_PREMIUM,
) -> dict:
    """Calculate Weighted Average Cost of Capital using CAPM.
    
    WACC = E/(E+D) * Re + D/(E+D) * Rd * (1-T)
    Re = Rf + Beta * ERP (CAPM)
    """
    info = ticker_obj.info or {}
    
    beta = info.get("beta", 1.0) or 1.0
    beta = max(0.5, min(3.0, beta))  # Clamp to reasonable range
    
    # Cost of equity (CAPM)
    cost_of_equity = risk_free_rate + beta * equity_risk_premium
    
    # Debt info
    total_debt = info.get("totalDebt", 0) or 0
    market_cap = info.get("marketCap", 0) or 0
    interest_expense = abs(info.get("interestExpense", 0) or 0)
    
    # Cost of debt
    if total_debt > 0 and interest_expense > 0:
        cost_of_debt = interest_expense / total_debt
    else:
        cost_of_debt = risk_free_rate + 0.02  # Risk-free + 200bps spread
    
    # Tax rate
    tax_provision = info.get("incomeTaxExpense", 0) or 0
    pretax_income = info.get("incomeBeforeTax", 0) or 0
    if pretax_income > 0 and tax_provision > 0:
        tax_rate = min(0.35, tax_provision / pretax_income)
    else:
        tax_rate = 0.21  # US corporate rate
    
    # Capital structure weights
    total_capital = market_cap + total_debt
    if total_capital > 0:
        equity_weight = market_cap / total_capital
        debt_weight = total_debt / total_capital
    else:
        equity_weight = 1.0
        debt_weight = 0.0
    
    wacc = equity_weight * cost_of_equity + debt_weight * cost_of_debt * (1 - tax_rate)
    
    return {
        "wacc": round(wacc, 4),
        "cost_of_equity": round(cost_of_equity, 4),
        "cost_of_debt": round(cost_of_debt, 4),
        "beta": round(beta, 2),
        "risk_free_rate": risk_free_rate,
        "equity_risk_premium": equity_risk_premium,
        "tax_rate": round(tax_rate, 3),
        "equity_weight": round(equity_weight, 3),
        "debt_weight": round(debt_weight, 3),
    }


def run_dcf(
    ticker: str,
    growth_rate: Optional[float] = None,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    equity_risk_premium: float = DEFAULT_EQUITY_RISK_PREMIUM,
) -> dict:
    """Run full DCF analysis for a ticker.
    
    Returns intrinsic value per share, margin of safety, and sensitivity table.
    """
    ticker = ticker.upper()
    
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        return {"ticker": ticker, "error": f"Failed to fetch data: {e}"}
    
    # Get FCF
    fcf = _get_fcf_from_yfinance(t)
    if not fcf or fcf <= 0:
        return {
            "ticker": ticker,
            "error": "No positive FCF available for DCF analysis",
            "fcf": fcf,
        }
    
    # Growth rate
    if growth_rate is None:
        growth_rate = _estimate_growth_rate(t)
    
    # WACC
    wacc_data = calculate_wacc(t, risk_free_rate, equity_risk_premium)
    wacc = wacc_data["wacc"]
    
    if wacc <= terminal_growth:
        return {
            "ticker": ticker,
            "error": f"WACC ({wacc:.2%}) must be greater than terminal growth ({terminal_growth:.2%})",
            "wacc": wacc_data,
        }
    
    # Project FCF for 5 years
    projected_fcf = []
    current_fcf = fcf
    for year in range(1, PROJECTION_YEARS + 1):
        current_fcf *= (1 + growth_rate)
        projected_fcf.append({
            "year": year,
            "fcf": round(current_fcf, 0),
            "pv_factor": round(1 / (1 + wacc) ** year, 4),
            "pv_fcf": round(current_fcf / (1 + wacc) ** year, 0),
        })
    
    # Terminal value (Gordon Growth Model)
    terminal_fcf = projected_fcf[-1]["fcf"] * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    pv_terminal = terminal_value / (1 + wacc) ** PROJECTION_YEARS
    
    # Enterprise value
    pv_fcf_total = sum(p["pv_fcf"] for p in projected_fcf)
    enterprise_value = pv_fcf_total + pv_terminal
    
    # Equity value
    total_debt = info.get("totalDebt", 0) or 0
    cash = info.get("totalCash", 0) or 0
    equity_value = enterprise_value - total_debt + cash
    
    # Per share
    shares = info.get("sharesOutstanding", 0) or 0
    if shares <= 0:
        return {"ticker": ticker, "error": "No shares outstanding data"}
    
    intrinsic_value = equity_value / shares
    current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0) or 0
    
    margin_of_safety = ((intrinsic_value - current_price) / intrinsic_value * 100) if intrinsic_value > 0 else 0
    
    # Confidence check
    fcf_yield = fcf / (current_price * shares) * 100 if (current_price and shares) else 0
    sector = info.get("sector", "")
    confidence = "HIGH"
    
    # DCF unreliable for: low-FCF-yield growth stocks, financials/insurance
    if abs(margin_of_safety) > 50 and fcf_yield < 1.5:
        confidence = "LOW"  # High-growth, low FCF yield
    elif sector in ("Financial Services", "Insurance"):
        confidence = "LOW"  # FCF distorted by premiums/float
    elif fcf_yield > 12:
        confidence = "LOW"  # Abnormally high FCF yield, likely sector distortion
    elif abs(margin_of_safety) > 50:
        confidence = "MEDIUM"
    elif abs(margin_of_safety) > 30:
        confidence = "MEDIUM"
    
    # Sensitivity table: vary growth rate and WACC
    sensitivity = []
    growth_range = [growth_rate - 0.04, growth_rate - 0.02, growth_rate, growth_rate + 0.02, growth_rate + 0.04]
    wacc_range = [wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02]
    
    for gr in growth_range:
        row = {"growth_rate": round(gr, 3), "values": {}}
        for w in wacc_range:
            if w <= terminal_growth or w <= 0:
                row["values"][f"{w:.3f}"] = None
                continue
            # Quick DCF calc
            cf = fcf
            pv_sum = 0
            for yr in range(1, PROJECTION_YEARS + 1):
                cf *= (1 + gr)
                pv_sum += cf / (1 + w) ** yr
            tv = cf * (1 + terminal_growth) / (w - terminal_growth)
            pv_tv = tv / (1 + w) ** PROJECTION_YEARS
            ev = pv_sum + pv_tv - total_debt + cash
            iv = ev / shares if shares > 0 else 0
            row["values"][f"{w:.3f}"] = round(iv, 2)
        sensitivity.append(row)
    
    return {
        "ticker": ticker,
        "company_name": info.get("shortName", ticker),
        "current_price": round(current_price, 2),
        "intrinsic_value": round(intrinsic_value, 2),
        "margin_of_safety": round(margin_of_safety, 2),
        "upside_pct": round((intrinsic_value / current_price - 1) * 100, 2) if current_price > 0 else None,
        "verdict": "UNDERVALUED" if margin_of_safety > 15 else "FAIRLY_VALUED" if margin_of_safety > -10 else "OVERVALUED",
        "confidence": confidence,
        "fcf_yield_pct": round(fcf_yield, 2),
        "assumptions": {
            "fcf_ttm": round(fcf, 0),
            "growth_rate": round(growth_rate, 4),
            "terminal_growth": terminal_growth,
            "projection_years": PROJECTION_YEARS,
        },
        "wacc": wacc_data,
        "projections": projected_fcf,
        "terminal_value": round(terminal_value, 0),
        "pv_terminal": round(pv_terminal, 0),
        "pv_fcf_total": round(pv_fcf_total, 0),
        "enterprise_value": round(enterprise_value, 0),
        "equity_value": round(equity_value, 0),
        "total_debt": total_debt,
        "cash": cash,
        "shares_outstanding": shares,
        "sensitivity": sensitivity,
    }


def get_dcf_summary(ticker: str) -> dict:
    """Quick summary: just intrinsic value + margin of safety."""
    result = run_dcf(ticker)
    if "error" in result:
        return result
    return {
        "ticker": result["ticker"],
        "company_name": result.get("company_name"),
        "current_price": result["current_price"],
        "intrinsic_value": result["intrinsic_value"],
        "margin_of_safety": result["margin_of_safety"],
        "upside_pct": result.get("upside_pct"),
        "verdict": result["verdict"],
        "wacc": result["wacc"]["wacc"],
        "growth_rate": result["assumptions"]["growth_rate"],
        "confidence": result.get("confidence", "HIGH"),
        "fcf_yield_pct": result.get("fcf_yield_pct"),
    }
