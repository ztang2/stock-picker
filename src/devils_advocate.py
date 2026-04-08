"""Devil's Advocate Review — automated risk check before buying.

Collects all available data and asks: "Why should we NOT buy this stock?"
Uses Gemini for qualitative risk assessment on top of quantitative flags.

Inspired by TradingAgents' Bull/Bear debate mechanism, but lightweight:
one focused LLM call instead of multi-agent rounds.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Optional

import yfinance as yf
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Gemini setup
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)


def _collect_data(ticker: str) -> Dict:
    """Collect all available data for a ticker."""
    data = {"ticker": ticker, "timestamp": datetime.now().isoformat()}

    # yfinance basics
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        data["company_name"] = info.get("shortName", ticker)
        data["sector"] = info.get("sector", "Unknown")
        data["industry"] = info.get("industry", "Unknown")
        data["current_price"] = info.get("currentPrice", 0)
        data["forward_pe"] = info.get("forwardPE")
        data["trailing_pe"] = info.get("trailingPE")
        data["profit_margin"] = info.get("profitMargins", 0)
        data["roe"] = info.get("returnOnEquity", 0)
        data["revenue_growth"] = info.get("revenueGrowth", 0)
        data["earnings_growth"] = info.get("earningsGrowth", 0)
        data["beta"] = info.get("beta", 0)
        raw_de = info.get("debtToEquity", 0) or 0
        data["debt_to_equity"] = raw_de / 100  # yfinance returns as %; convert to ratio
        data["52w_high"] = info.get("fiftyTwoWeekHigh", 0)
        data["52w_low"] = info.get("fiftyTwoWeekLow", 0)
        data["analyst_target"] = info.get("targetMeanPrice", 0)
        data["recommendation"] = info.get("recommendationKey", "none")
        data["num_analysts"] = info.get("numberOfAnalystOpinions", 0)
        data["market_cap"] = info.get("marketCap", 0)
        data["short_pct"] = info.get("shortPercentOfFloat", 0)

        # RSI
        hist = t.history(period="1mo")
        if len(hist) > 14:
            delta = hist['Close'].diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            data["rsi"] = round(float(rsi.iloc[-1]), 1)

        # Insider transactions (2026 only)
        ins = t.insider_transactions
        if ins is not None and not ins.empty:
            recent = ins[ins['Start Date'] >= '2026-01-01']
            buys = []
            sells = []
            for _, row in recent.iterrows():
                text = str(row.get("Text", "")).lower()
                value = abs(row.get("Value", 0) or 0)
                title = str(row.get("Position", ""))
                if "purchase" in text or "buy" in text:
                    buys.append({"title": title, "value": value})
                elif "sale" in text:
                    sells.append({"title": title, "value": value})

            data["insider_buys_2026"] = len(buys)
            data["insider_buy_value"] = sum(b["value"] for b in buys)
            data["insider_sells_2026"] = len(sells)
            data["insider_sell_value"] = sum(s["value"] for s in sells)
            data["insider_details"] = {
                "buys": buys[:5],  # top 5
                "sells": sells[:5],
            }

        # Earnings history
        earn = t.earnings_history
        if earn is not None and not earn.empty:
            surprises = []
            for _, row in earn.iterrows():
                surprises.append({
                    "actual": row.get("epsActual"),
                    "estimate": row.get("epsEstimate"),
                    "surprise_pct": round(float(row.get("surprisePercent", 0) or 0) * 100, 1),
                })
            data["earnings_history"] = surprises

    except Exception as e:
        logger.warning(f"yfinance data collection failed for {ticker}: {e}")
        data["yfinance_error"] = str(e)

    # Pipeline data
    try:
        results_file = os.path.join(os.path.dirname(__file__), "..", "data", "scan_results.json")
        with open(results_file) as f:
            scan = json.load(f)
        for s in scan.get("all_scores", []):
            if s.get("ticker") == ticker:
                data["pipeline_rank"] = s.get("rank")
                data["pipeline_score"] = s.get("composite_score")
                data["fundamentals_pct"] = s.get("fundamentals_pct")
                data["valuation_pct"] = s.get("valuation_pct")
                data["growth_pct"] = s.get("growth_pct")
                data["technicals_pct"] = s.get("technicals_pct")
                data["entry_signal"] = s.get("entry_signal")
                break
    except Exception:
        pass

    # Momentum data
    try:
        from .early_momentum import compute_momentum
        mom = compute_momentum(ticker)
        data["momentum_score"] = mom.get("composite_score")
        data["momentum_signal"] = mom.get("signal")
        data["momentum_signals"] = {}
        for k, v in mom.get("signals", {}).items():
            data["momentum_signals"][k] = v.get("score", 0)
    except Exception:
        pass

    # Quality data
    try:
        from .quality_scores import compute_quality
        qual = compute_quality(ticker)
        data["piotroski"] = qual.get("piotroski", {}).get("score")
        data["altman_z"] = qual.get("altman_z", {}).get("score")
        data["altman_zone"] = qual.get("altman_z", {}).get("zone")
    except Exception:
        pass

    return data


def _build_prompt(data: Dict) -> str:
    """Build the Devil's Advocate prompt."""
    ticker = data["ticker"]
    name = data.get("company_name", ticker)

    prompt = f"""You are a skeptical investment analyst. Your job is to find EVERY reason NOT to buy {ticker} ({name}).

Be brutally honest. Do not sugarcoat. Flag every risk, no matter how small.

## Data:
{json.dumps(data, indent=2, default=str)}

## Your task:
1. List ALL red flags (🚩) with severity: CRITICAL / HIGH / MEDIUM / LOW
2. For each flag, explain WHY it's a concern in 1-2 sentences
3. Check specifically:
   - Insider selling patterns (C-suite selling = very bad)
   - AI/technology disruption risk to the business
   - Debt levels and financial health
   - Growth trajectory (slowing?)
   - Valuation vs peers
   - Sector/macro headwinds
   - Recent news or catalysts that could go wrong
4. List any GREEN flags (✅) — things that ARE genuinely good
5. Give an overall RISK SCORE from 1-10 (10 = extremely risky, do not buy)
6. Final verdict: BUY / CAUTIOUS BUY / WAIT / DO NOT BUY

Respond in Chinese (简体中文). Be specific with numbers and data.
Format clearly with emoji flags.
"""
    return prompt


def review(ticker: str) -> Dict:
    """Run Devil's Advocate review on a ticker.

    Returns dict with: data, red_flags, green_flags, risk_score, verdict, review_text
    """
    # Collect all data
    data = _collect_data(ticker)

    # Generate quantitative flags first (no LLM needed)
    quant_flags = _quantitative_flags(data)

    # If no Gemini key, return quant-only review
    if not GEMINI_KEY:
        return {
            "ticker": ticker,
            "data": data,
            "quant_flags": quant_flags,
            "review_text": "⚠️ Gemini API key not configured. Showing quantitative flags only.",
            "risk_score": quant_flags.get("risk_score", 5),
            "source": "quantitative_only",
        }

    # Call Gemini for qualitative review
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = _build_prompt(data)
        response = model.generate_content(prompt)
        review_text = response.text

        # Extract risk score from response
        risk_score = quant_flags.get("risk_score", 5)
        for line in review_text.split("\n"):
            if "RISK SCORE" in line.upper() or "风险评分" in line or "风险分数" in line:
                import re
                nums = re.findall(r'(\d+)/10', line)
                if nums:
                    risk_score = int(nums[0])
                    break

        return {
            "ticker": ticker,
            "company_name": data.get("company_name", ticker),
            "data_summary": {
                "price": data.get("current_price"),
                "pe": data.get("forward_pe"),
                "pipeline_rank": data.get("pipeline_rank"),
                "pipeline_score": data.get("pipeline_score"),
                "insider_buys": data.get("insider_buys_2026", 0),
                "insider_buy_value": data.get("insider_buy_value", 0),
                "insider_sells": data.get("insider_sells_2026", 0),
                "insider_sell_value": data.get("insider_sell_value", 0),
                "momentum": data.get("momentum_score"),
                "piotroski": data.get("piotroski"),
            },
            "quant_flags": quant_flags,
            "review_text": review_text,
            "risk_score": risk_score,
            "source": "gemini_review",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Gemini review failed for {ticker}: {e}")
        return {
            "ticker": ticker,
            "data": data,
            "quant_flags": quant_flags,
            "review_text": f"⚠️ Gemini review failed: {e}. Showing quantitative flags only.",
            "risk_score": quant_flags.get("risk_score", 5),
            "source": "quantitative_only_fallback",
        }


def _quantitative_flags(data: Dict) -> Dict:
    """Generate purely quantitative red/green flags."""
    red_flags = []
    green_flags = []
    risk_score = 3  # start neutral

    # Insider selling
    sells = data.get("insider_sells_2026", 0)
    sell_val = data.get("insider_sell_value", 0)
    buys = data.get("insider_buys_2026", 0)
    buy_val = data.get("insider_buy_value", 0)

    if sell_val > 10_000_000 and buys == 0:
        red_flags.append({
            "flag": "🚩 CRITICAL: Insider大量抛售",
            "detail": f"2026年卖出${sell_val:,.0f}，{sells}笔交易，0买入",
            "severity": "CRITICAL",
        })
        risk_score += 3
    elif sell_val > 5_000_000 and buys == 0:
        red_flags.append({
            "flag": "🚩 HIGH: Insider明显卖出",
            "detail": f"2026年卖出${sell_val:,.0f}，0买入",
            "severity": "HIGH",
        })
        risk_score += 2
    elif sell_val > 1_000_000 and buys == 0:
        red_flags.append({
            "flag": "⚠️ MEDIUM: Insider卖出",
            "detail": f"2026年卖出${sell_val:,.0f}，0买入",
            "severity": "MEDIUM",
        })
        risk_score += 1

    if buy_val > 1_000_000:
        green_flags.append({
            "flag": f"✅ Insider买入${buy_val:,.0f}",
            "detail": f"{buys}笔买入交易",
        })
        risk_score -= 1

    # Earnings growth
    eg = data.get("earnings_growth", 0)
    if eg and eg < -0.2:
        red_flags.append({
            "flag": "🚩 HIGH: 盈利大幅下降",
            "detail": f"Earnings growth: {eg*100:.1f}%",
            "severity": "HIGH",
        })
        risk_score += 2
    elif eg and eg > 0.2:
        green_flags.append({
            "flag": f"✅ 盈利强劲增长 {eg*100:.1f}%",
            "detail": "",
        })

    # Debt
    de = data.get("debt_to_equity", 0)
    if de and de > 2.0:
        red_flags.append({
            "flag": "🚩 HIGH: 高负债",
            "detail": f"Debt/Equity: {de:.2f}",
            "severity": "HIGH",
        })
        risk_score += 1
    elif de and de < 0.5:
        green_flags.append({
            "flag": f"✅ 低负债 D/E={de:.2f}",
            "detail": "",
        })

    # Near 52w high (buying at the top)
    price = data.get("current_price", 0)
    high52 = data.get("52w_high", 0)
    if price and high52 and price > high52 * 0.95:
        red_flags.append({
            "flag": "⚠️ MEDIUM: 接近52周高点",
            "detail": f"当前${price:.2f} vs 高点${high52:.2f} (-{(1-price/high52)*100:.1f}%)",
            "severity": "MEDIUM",
        })
        risk_score += 1

    # Analyst target below current price
    target = data.get("analyst_target", 0)
    if price and target and target < price:
        red_flags.append({
            "flag": "🚩 HIGH: Analyst目标价低于当前价",
            "detail": f"Target ${target:.2f} vs Current ${price:.2f} ({(target/price-1)*100:+.1f}%)",
            "severity": "HIGH",
        })
        risk_score += 1
    elif price and target and target > price * 1.2:
        green_flags.append({
            "flag": f"✅ Analyst目标价+{(target/price-1)*100:.0f}%上行空间",
            "detail": f"Target ${target:.2f}",
        })

    # Piotroski
    pio = data.get("piotroski")
    if pio is not None and pio <= 3:
        red_flags.append({
            "flag": "🚩 HIGH: Piotroski低分",
            "detail": f"Piotroski F-Score: {pio}/9 (质量差)",
            "severity": "HIGH",
        })
        risk_score += 1
    elif pio is not None and pio >= 7:
        green_flags.append({
            "flag": f"✅ Piotroski高分 {pio}/9",
            "detail": "财务质量好",
        })

    # Altman Z distress
    az = data.get("altman_z")
    zone = data.get("altman_zone", "")
    if zone and "distress" in zone.lower():
        red_flags.append({
            "flag": "🚩 CRITICAL: Altman Z破产风险",
            "detail": f"Z-Score: {az:.2f} (distress zone <1.8)",
            "severity": "CRITICAL",
        })
        risk_score += 2

    # RSI overbought
    rsi = data.get("rsi")
    if rsi and rsi > 70:
        red_flags.append({
            "flag": "⚠️ MEDIUM: RSI超买",
            "detail": f"RSI: {rsi:.1f} (>70 overbought)",
            "severity": "MEDIUM",
        })
        risk_score += 1
    elif rsi and rsi < 30:
        green_flags.append({
            "flag": f"✅ RSI极度超卖 {rsi:.1f}",
            "detail": "可能反弹机会",
        })

    # Clamp risk score
    risk_score = max(1, min(10, risk_score))

    return {
        "red_flags": red_flags,
        "green_flags": green_flags,
        "risk_score": risk_score,
        "red_count": len(red_flags),
        "green_count": len(green_flags),
    }
