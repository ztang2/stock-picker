"""Generate one-liner thesis explaining why a stock is interesting right now."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_thesis(stock: dict) -> str:
    """Generate a template-based thesis from scan result data.

    Args:
        stock: A stock dict from scan results (top or all_scores format).

    Returns:
        A one-liner thesis string, e.g.:
        "RSI 28 (oversold) + $4M insider buying. 32% below analyst target."
    """
    points = []

    # RSI extremes
    rsi = stock.get("rsi")
    if rsi is not None:
        if rsi < 30:
            points.append(("rsi_oversold", 10, f"RSI {rsi:.0f} (oversold)"))
        elif rsi < 35:
            points.append(("rsi_low", 5, f"RSI {rsi:.0f} (near oversold)"))
        elif rsi > 70:
            points.append(("rsi_overbought", 8, f"RSI {rsi:.0f} (overbought)"))

    # Insider activity
    insider_buy = stock.get("insider_buy_value") or 0
    insider_sell = stock.get("insider_sell_value") or 0
    if insider_buy > 1_000_000:
        points.append(("insider_buy", 9, f"${insider_buy / 1e6:.1f}M insider buying"))
    elif insider_buy > 100_000:
        points.append(("insider_buy", 6, f"${insider_buy / 1e3:.0f}K insider buying"))
    if insider_sell > 1_000_000:
        points.append(("insider_sell", 7, f"${insider_sell / 1e6:.1f}M insider selling"))

    # Earnings streak
    consecutive = stock.get("consecutive_days") or 0
    if consecutive >= 5:
        points.append(("streak", 7, f"{consecutive}-day streak in top 20"))

    # Analyst target upside
    sentiment = stock.get("sentiment")
    if isinstance(sentiment, dict):
        pt_upside = sentiment.get("pt_upside_pct") or 0
        if pt_upside > 0.2:
            points.append(("target_upside", 8, f"{pt_upside * 100:.0f}% below analyst target"))
        recommendation = sentiment.get("recommendation", "")
        if recommendation in ("strongBuy", "buy"):
            analyst_count = sentiment.get("analyst_count", 0)
            if analyst_count >= 5:
                points.append(("analyst_buy", 5, f"analysts say {recommendation} ({analyst_count})"))

    # ADX strength
    adx = stock.get("adx")
    if adx is not None and adx > 30:
        points.append(("adx_strong", 6, f"ADX {adx:.0f} (strong trend)"))

    # Valuation
    pe = stock.get("pe_ratio")
    if pe is not None and 0 < pe < 12:
        points.append(("low_pe", 5, f"P/E {pe:.1f}"))

    # DCF upside
    dcf_mos = stock.get("dcf_margin_of_safety")
    if dcf_mos is not None and dcf_mos > 20:
        points.append(("dcf_undervalued", 7, f"{dcf_mos:.0f}% DCF margin of safety"))

    # Revenue growth
    rev_growth = stock.get("revenue_growth")
    if rev_growth is not None and rev_growth > 0.15:
        points.append(("rev_growth", 5, f"{rev_growth * 100:.0f}% revenue growth"))

    # Quality
    piotroski = stock.get("piotroski_score")
    if piotroski is not None and piotroski >= 7:
        points.append(("piotroski", 4, f"Piotroski {piotroski}/9"))

    # Smart money
    smart_money = stock.get("smart_money_score")
    if smart_money is not None and smart_money > 70:
        points.append(("smart_money", 6, f"smart money score {smart_money:.0f}"))

    if not points:
        return "No standout signals"

    # Sort by priority (descending), take top 3
    points.sort(key=lambda x: x[1], reverse=True)
    top = points[:3]
    return " + ".join(p[2] for p in top)


def generate_gemini_thesis(ticker: str) -> Optional[dict]:
    """Generate a Gemini-powered bull thesis for a stock.

    Returns: {ticker, thesis, source: "gemini"} or None on failure.
    """
    import os

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    from .devils_advocate import _collect_data
    data = _collect_data(ticker)

    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""You are a bullish stock analyst. Given this data for {ticker} ({data.get('company_name', ticker)}), \
write a concise 2-3 sentence investment thesis explaining why NOW is a good time to buy this stock.

Focus on: entry timing, catalysts, valuation, momentum, and any unique advantages.
Be specific with numbers. Don't hedge — make a confident case.

Data:
- Sector: {data.get('sector')} / {data.get('industry')}
- Price: ${data.get('current_price')}
- Forward P/E: {data.get('forward_pe')}
- Revenue Growth: {(data.get('revenue_growth', 0) or 0) * 100:.1f}%
- Earnings Growth: {(data.get('earnings_growth', 0) or 0) * 100:.1f}%
- Profit Margin: {(data.get('profit_margin', 0) or 0) * 100:.1f}%
- ROE: {(data.get('roe', 0) or 0) * 100:.1f}%
- Beta: {data.get('beta')}
- D/E: {data.get('debt_to_equity', 0):.2f}
- 52w Range: ${data.get('52w_low')} - ${data.get('52w_high')}
- Analyst Target: ${data.get('analyst_target')} ({data.get('recommendation')})
- Insider Buys 2026: {data.get('insider_buys_count', 0)} totaling ${data.get('insider_buy_value', 0):,.0f}
"""

    try:
        response = model.generate_content(prompt)
        return {"ticker": ticker, "thesis": response.text.strip(), "source": "gemini"}
    except Exception as e:
        logger.warning("Gemini thesis failed for %s: %s", ticker, e)
        return None
