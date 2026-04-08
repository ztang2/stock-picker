"""Company intelligence: news, analyst ratings, and business summary for top stocks.

Fills the gap between quantitative scoring and qualitative understanding.
Uses yfinance for news/analyst data, web search for deeper context.
"""

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
INTEL_CACHE_FILE = DATA_DIR / "company_intel_cache.json"
CACHE_TTL_HOURS = 12  # Refresh every 12 hours


def _load_cache() -> dict:
    if INTEL_CACHE_FILE.exists():
        try:
            return json.loads(INTEL_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(data: dict):
    INTEL_CACHE_FILE.write_text(json.dumps(data, indent=2, default=str))


def get_company_intel(ticker: str, force_refresh: bool = False) -> dict:
    """Get comprehensive company intelligence for a single ticker.
    
    Returns:
        dict with keys: ticker, name, sector, industry, description,
        market_cap, news, analyst_ratings, key_stats
    """
    # Check cache
    cache = _load_cache()
    cached = cache.get(ticker)
    if cached and not force_refresh:
        cached_at = cached.get("cached_at", "")
        if cached_at:
            try:
                age = datetime.now() - datetime.fromisoformat(cached_at)
                if age < timedelta(hours=CACHE_TTL_HOURS):
                    return cached
            except Exception:
                pass
    
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        
        # Basic company info
        intel = {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName", ticker),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "description": _truncate(info.get("longBusinessSummary", ""), 300),
            "market_cap": info.get("marketCap", 0),
            "market_cap_str": _format_market_cap(info.get("marketCap", 0)),
            "employees": info.get("fullTimeEmployees", 0),
            "website": info.get("website", ""),
            "country": info.get("country", ""),
        }
        
        # Key financial stats
        intel["key_stats"] = {
            "pe_forward": info.get("forwardPE"),
            "pe_trailing": info.get("trailingPE"),
            "peg_ratio": info.get("pegRatio"),
            "profit_margin": _pct(info.get("profitMargins")),
            "revenue_growth": _pct(info.get("revenueGrowth")),
            "earnings_growth": _pct(info.get("earningsGrowth")),
            "debt_to_equity": (info.get("debtToEquity") or 0) / 100,
            "current_ratio": info.get("currentRatio"),
            "roe": _pct(info.get("returnOnEquity")),
            "free_cash_flow": info.get("freeCashflow"),
            "dividend_yield": _pct(info.get("dividendYield")),
            "beta": info.get("beta"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        }
        
        # News
        try:
            news_raw = tk.news or []
            intel["news"] = []
            for n in news_raw[:8]:  # Top 8 news items
                content = n.get("content", {}) if isinstance(n.get("content"), dict) else {}
                intel["news"].append({
                    "title": content.get("title") or n.get("title", ""),
                    "publisher": content.get("provider", {}).get("displayName") or n.get("publisher", ""),
                    "published": content.get("pubDate") or n.get("providerPublishTime", ""),
                    "link": content.get("canonicalUrl", {}).get("url") or n.get("link", ""),
                })
        except Exception as e:
            logger.warning(f"News fetch failed for {ticker}: {e}")
            intel["news"] = []
        
        # Analyst recommendations
        try:
            recs = tk.recommendations
            if recs is not None and not recs.empty:
                latest = recs.tail(5).to_dict("records")
                intel["analyst_ratings"] = latest
            else:
                intel["analyst_ratings"] = []
        except Exception as e:
            logger.warning(f"Recommendations failed for {ticker}: {e}")
            intel["analyst_ratings"] = []
        
        # Analyst price targets
        try:
            targets = tk.analyst_price_targets
            if targets:
                intel["price_targets"] = {
                    "current": targets.get("current"),
                    "low": targets.get("low"),
                    "high": targets.get("high"),
                    "mean": targets.get("mean"),
                    "median": targets.get("median"),
                }
            else:
                intel["price_targets"] = {}
        except Exception:
            intel["price_targets"] = {}
        
        # Recommendation summary (buy/hold/sell counts)
        try:
            rec_summary = tk.recommendations_summary
            if rec_summary is not None and not rec_summary.empty:
                latest_row = rec_summary.iloc[0].to_dict()
                intel["recommendation_summary"] = {
                    "strong_buy": latest_row.get("strongBuy", 0),
                    "buy": latest_row.get("buy", 0),
                    "hold": latest_row.get("hold", 0),
                    "sell": latest_row.get("sell", 0),
                    "strong_sell": latest_row.get("strongSell", 0),
                }
            else:
                intel["recommendation_summary"] = {}
        except Exception:
            intel["recommendation_summary"] = {}
        
        intel["cached_at"] = datetime.now().isoformat()
        
        # Update cache
        cache[ticker] = intel
        _save_cache(cache)
        
        return intel
        
    except Exception as e:
        logger.error(f"Company intel failed for {ticker}: {e}")
        return {"ticker": ticker, "error": str(e)}


def get_top_intel(n: int = 20) -> List[dict]:
    """Get company intelligence for top N stocks from latest scan.
    
    Reads scan_results.json and fetches intel for top N tickers.
    """
    scan_file = DATA_DIR / "scan_results.json"
    if not scan_file.exists():
        return []
    
    try:
        scan_data = json.loads(scan_file.read_text())
        top_tickers = [s["ticker"] for s in scan_data.get("top", [])[:n]]
    except Exception:
        return []
    
    results = []
    for ticker in top_tickers:
        intel = get_company_intel(ticker)
        # Add scan score info
        score_data = next(
            (s for s in scan_data.get("top", []) if s["ticker"] == ticker), {}
        )
        intel["scan_score"] = score_data.get("composite_score", 0)
        intel["scan_signal"] = score_data.get("entry_signal", "?")
        intel["scan_rank"] = top_tickers.index(ticker) + 1
        results.append(intel)
    
    return results


def format_intel_summary(intel: dict) -> str:
    """Format a single company's intel as a readable summary."""
    if "error" in intel:
        return f"**{intel['ticker']}** — Error: {intel['error']}"
    
    lines = []
    
    # Header
    rank = intel.get("scan_rank", "?")
    score = intel.get("scan_score", 0)
    signal = intel.get("scan_signal", "?")
    lines.append(f"**#{rank} {intel['ticker']} — {intel.get('name', '?')}** (Score: {score:.1f}, {signal})")
    
    # Company basics
    lines.append(f"📍 {intel.get('sector', '?')} / {intel.get('industry', '?')} | {intel.get('market_cap_str', '?')} mkt cap")
    
    # Description (truncated)
    desc = intel.get("description", "")
    if desc:
        lines.append(f"📝 {desc}")
    
    # Key stats
    stats = intel.get("key_stats", {})
    stat_parts = []
    if stats.get("pe_forward"):
        stat_parts.append(f"PE {stats['pe_forward']:.1f}")
    if stats.get("profit_margin"):
        stat_parts.append(f"Margin {stats['profit_margin']}")
    if stats.get("revenue_growth"):
        stat_parts.append(f"Rev Growth {stats['revenue_growth']}")
    if stats.get("roe"):
        stat_parts.append(f"ROE {stats['roe']}")
    if stats.get("debt_to_equity") is not None:
        stat_parts.append(f"D/E {stats['debt_to_equity']:.2f}")
    if stat_parts:
        lines.append(f"📊 {' | '.join(stat_parts)}")
    
    # Price targets
    pt = intel.get("price_targets", {})
    if pt.get("median") and stats.get("current_price"):
        upside = (pt["median"] - stats["current_price"]) / stats["current_price"] * 100
        lines.append(f"🎯 Analyst target: ${pt['median']:.0f} ({upside:+.0f}%) | Range: ${pt.get('low', 0):.0f}-${pt.get('high', 0):.0f}")
    
    # Recommendation summary
    rec = intel.get("recommendation_summary", {})
    if rec:
        total = sum(rec.values())
        if total > 0:
            buy_pct = (rec.get("strong_buy", 0) + rec.get("buy", 0)) / total * 100
            lines.append(f"👥 Analysts: {rec.get('strong_buy',0)} Strong Buy, {rec.get('buy',0)} Buy, {rec.get('hold',0)} Hold, {rec.get('sell',0)} Sell ({buy_pct:.0f}% bullish)")
    
    # Recent news
    news = intel.get("news", [])
    if news:
        lines.append("📰 Recent:")
        for n in news[:3]:
            title = n.get("title", "")
            publisher = n.get("publisher", "")
            if title:
                lines.append(f"  • {title} ({publisher})")
    
    return "\n".join(lines)


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len-3] + "..."


def _format_market_cap(mc: int) -> str:
    if not mc:
        return "?"
    if mc >= 1e12:
        return f"${mc/1e12:.1f}T"
    if mc >= 1e9:
        return f"${mc/1e9:.1f}B"
    if mc >= 1e6:
        return f"${mc/1e6:.0f}M"
    return f"${mc:,.0f}"


def _pct(val) -> Optional[str]:
    if val is None:
        return None
    try:
        return f"{float(val)*100:.1f}%"
    except (TypeError, ValueError):
        return None
