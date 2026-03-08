"""Financial quality scores: Piotroski F-Score and Altman Z-Score.

Piotroski F-Score (0-9): Measures financial strength improvement.
  9 = perfect financial health, improving on all metrics
  0 = deteriorating on all metrics
  Typically: 8-9 = very strong, 5-7 = average, 0-4 = weak

Altman Z-Score: Predicts bankruptcy probability within 2 years.
  > 3.0 = safe zone (very low bankruptcy risk)
  1.8-3.0 = grey zone (moderate risk)
  < 1.8 = distress zone (high risk)

Both scores use existing yfinance data — no new API needed.
"""

import logging
from typing import Dict, Optional, Tuple

import yfinance as yf

logger = logging.getLogger(__name__)


def compute_piotroski(ticker: str) -> Dict:
    """Compute Piotroski F-Score (0-9) from financial statements.
    
    9 criteria across profitability, leverage, and operating efficiency.
    """
    try:
        t = yf.Ticker(ticker)
        
        # Get financial statements
        income = t.financials
        balance = t.balance_sheet
        cashflow = t.cashflow
        
        if income is None or balance is None or cashflow is None:
            return {"score": None, "error": "Missing financial data"}
        if income.empty or balance.empty or cashflow.empty:
            return {"score": None, "error": "Empty financial data"}
        
        # Need at least 2 years for year-over-year comparison
        if len(income.columns) < 2 or len(balance.columns) < 2:
            return {"score": None, "error": "Need 2+ years of data"}
        
        score = 0
        details = {}
        
        # Helper to safely get values
        def get(df, row_names, col_idx=0):
            for name in row_names:
                if name in df.index:
                    val = df.iloc[df.index.get_loc(name), col_idx]
                    if val is not None and str(val) != 'nan':
                        return float(val)
            return None
        
        # Current and previous year
        total_assets_curr = get(balance, ['Total Assets'])
        total_assets_prev = get(balance, ['Total Assets'], 1)
        
        if not total_assets_curr or not total_assets_prev:
            return {"score": None, "error": "Missing total assets"}
        
        # === PROFITABILITY (4 points) ===
        
        # 1. ROA > 0 (net income / total assets)
        net_income = get(income, ['Net Income', 'Net Income Common Stockholders'])
        if net_income is not None:
            roa = net_income / total_assets_curr
            details['roa'] = round(roa, 4)
            if roa > 0:
                score += 1
                details['roa_positive'] = True
            else:
                details['roa_positive'] = False
        
        # 2. Operating Cash Flow > 0
        ocf = get(cashflow, ['Operating Cash Flow', 'Total Cash From Operating Activities',
                             'Cash Flow From Continuing Operating Activities'])
        if ocf is not None:
            details['ocf'] = round(ocf / 1e6, 1)
            if ocf > 0:
                score += 1
                details['ocf_positive'] = True
            else:
                details['ocf_positive'] = False
        
        # 3. ROA increasing (current year ROA > previous year ROA)
        net_income_prev = get(income, ['Net Income', 'Net Income Common Stockholders'], 1)
        if net_income is not None and net_income_prev is not None:
            roa_curr = net_income / total_assets_curr
            roa_prev = net_income_prev / total_assets_prev
            if roa_curr > roa_prev:
                score += 1
                details['roa_increasing'] = True
            else:
                details['roa_increasing'] = False
        
        # 4. Cash flow > Net Income (accruals quality)
        if ocf is not None and net_income is not None:
            if ocf > net_income:
                score += 1
                details['accruals_quality'] = True
            else:
                details['accruals_quality'] = False
        
        # === LEVERAGE / LIQUIDITY (3 points) ===
        
        # 5. Long-term debt ratio decreasing
        ltd_curr = get(balance, ['Long Term Debt', 'Long Term Debt And Capital Lease Obligation'])
        ltd_prev = get(balance, ['Long Term Debt', 'Long Term Debt And Capital Lease Obligation'], 1)
        if ltd_curr is not None and ltd_prev is not None and total_assets_curr and total_assets_prev:
            ltd_ratio_curr = ltd_curr / total_assets_curr
            ltd_ratio_prev = ltd_prev / total_assets_prev
            if ltd_ratio_curr <= ltd_ratio_prev:
                score += 1
                details['leverage_decreasing'] = True
            else:
                details['leverage_decreasing'] = False
        elif ltd_curr is None or ltd_curr == 0:
            # No debt = pass
            score += 1
            details['leverage_decreasing'] = True
        
        # 6. Current ratio increasing
        ca_curr = get(balance, ['Current Assets'])
        cl_curr = get(balance, ['Current Liabilities'])
        ca_prev = get(balance, ['Current Assets'], 1)
        cl_prev = get(balance, ['Current Liabilities'], 1)
        if ca_curr and cl_curr and ca_prev and cl_prev and cl_curr > 0 and cl_prev > 0:
            cr_curr = ca_curr / cl_curr
            cr_prev = ca_prev / cl_prev
            details['current_ratio'] = round(cr_curr, 2)
            if cr_curr > cr_prev:
                score += 1
                details['current_ratio_increasing'] = True
            else:
                details['current_ratio_increasing'] = False
        
        # 7. No new shares issued (dilution check)
        shares_curr = get(balance, ['Share Issued', 'Ordinary Shares Number', 'Common Stock'])
        shares_prev = get(balance, ['Share Issued', 'Ordinary Shares Number', 'Common Stock'], 1)
        if shares_curr is not None and shares_prev is not None:
            if shares_curr <= shares_prev:
                score += 1
                details['no_dilution'] = True
            else:
                details['no_dilution'] = False
        
        # === OPERATING EFFICIENCY (2 points) ===
        
        # 8. Gross margin increasing
        gp_curr = get(income, ['Gross Profit'])
        rev_curr = get(income, ['Total Revenue', 'Revenue'])
        gp_prev = get(income, ['Gross Profit'], 1)
        rev_prev = get(income, ['Total Revenue', 'Revenue'], 1)
        if gp_curr and rev_curr and gp_prev and rev_prev and rev_curr > 0 and rev_prev > 0:
            gm_curr = gp_curr / rev_curr
            gm_prev = gp_prev / rev_prev
            details['gross_margin'] = round(gm_curr, 4)
            if gm_curr > gm_prev:
                score += 1
                details['gross_margin_increasing'] = True
            else:
                details['gross_margin_increasing'] = False
        
        # 9. Asset turnover increasing (revenue / total assets)
        if rev_curr and rev_prev and total_assets_curr and total_assets_prev:
            at_curr = rev_curr / total_assets_curr
            at_prev = rev_prev / total_assets_prev
            if at_curr > at_prev:
                score += 1
                details['asset_turnover_increasing'] = True
            else:
                details['asset_turnover_increasing'] = False
        
        return {
            "score": score,
            "max_score": 9,
            "grade": "A" if score >= 8 else "B" if score >= 6 else "C" if score >= 4 else "D",
            "details": details,
        }
        
    except Exception as e:
        logger.warning(f"Piotroski failed for {ticker}: {e}")
        return {"score": None, "error": str(e)}


def compute_altman_z(ticker: str) -> Dict:
    """Compute Altman Z-Score for bankruptcy prediction.
    
    Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
    A = Working Capital / Total Assets
    B = Retained Earnings / Total Assets
    C = EBIT / Total Assets
    D = Market Cap / Total Liabilities
    E = Revenue / Total Assets
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
        balance = t.balance_sheet
        income = t.financials
        
        if balance is None or balance.empty or income is None or income.empty:
            return {"score": None, "error": "Missing financial data"}
        
        def get(df, row_names, col_idx=0):
            for name in row_names:
                if name in df.index:
                    val = df.iloc[df.index.get_loc(name), col_idx]
                    if val is not None and str(val) != 'nan':
                        return float(val)
            return None
        
        total_assets = get(balance, ['Total Assets'])
        if not total_assets or total_assets <= 0:
            return {"score": None, "error": "Missing total assets"}
        
        # A: Working Capital / Total Assets
        ca = get(balance, ['Current Assets'])
        cl = get(balance, ['Current Liabilities'])
        working_capital = (ca - cl) if (ca is not None and cl is not None) else None
        A = working_capital / total_assets if working_capital is not None else 0
        
        # B: Retained Earnings / Total Assets
        re = get(balance, ['Retained Earnings'])
        B = re / total_assets if re is not None else 0
        
        # C: EBIT / Total Assets
        ebit = get(income, ['EBIT', 'Operating Income'])
        C = ebit / total_assets if ebit is not None else 0
        
        # D: Market Cap / Total Liabilities
        market_cap = info.get('marketCap', 0)
        total_liabilities = get(balance, ['Total Liabilities Net Minority Interest', 'Total Liab'])
        D = market_cap / total_liabilities if (market_cap and total_liabilities and total_liabilities > 0) else 0
        
        # E: Revenue / Total Assets
        revenue = get(income, ['Total Revenue', 'Revenue'])
        E = revenue / total_assets if revenue is not None else 0
        
        z_score = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E
        
        if z_score > 3.0:
            zone = "safe"
        elif z_score > 1.8:
            zone = "grey"
        else:
            zone = "distress"
        
        return {
            "score": round(z_score, 2),
            "zone": zone,
            "components": {
                "working_capital_ratio": round(A, 4),
                "retained_earnings_ratio": round(B, 4),
                "ebit_ratio": round(C, 4),
                "market_cap_to_liabilities": round(D, 4),
                "asset_turnover": round(E, 4),
            },
        }
        
    except Exception as e:
        logger.warning(f"Altman Z failed for {ticker}: {e}")
        return {"score": None, "error": str(e)}


def compute_quality_scores(ticker: str) -> Dict:
    """Compute both Piotroski and Altman scores for a stock."""
    piotroski = compute_piotroski(ticker)
    altman = compute_altman_z(ticker)
    
    # Combined quality score (0-100)
    quality_score = None
    if piotroski.get("score") is not None and altman.get("score") is not None:
        # Piotroski: 0-9 → 0-50 points
        p_points = (piotroski["score"] / 9) * 50
        
        # Altman: map to 0-50 points
        # < 1.8 = 0, 1.8-3.0 = 10-30, > 3.0 = 30-50 (capped at z=10)
        z = altman["score"]
        if z < 1.8:
            a_points = max(0, z / 1.8 * 10)
        elif z <= 3.0:
            a_points = 10 + (z - 1.8) / 1.2 * 20
        else:
            a_points = 30 + min(20, (z - 3.0) / 7.0 * 20)
        
        quality_score = round(p_points + a_points, 1)
    
    return {
        "piotroski": piotroski,
        "altman": altman,
        "quality_score": quality_score,
    }
