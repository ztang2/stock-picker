"""Orchestrate the full stock screening pipeline."""

import json
import logging
import time
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd
import yaml
import yfinance as yf

from .universe import get_sp500_tickers
from .fundamentals import score_fundamentals
from .valuation import score_valuation
from .technicals import score_technicals
from .risk import score_risk
from .growth import score_growth
from .scorer import compute_composite
from .sector import compute_sector_relative_scores
from .momentum import compute_momentum
from .sell_signals import compute_sell_signals
from .strategies import get_strategy
from .earnings_guard import apply_earnings_guard
from .freshness import check_freshness
from .streak_tracker import update_streaks, add_streaks_to_results
from .sentiment import analyze_sentiment
from .market_regime import detect_market_regime
from .insider import get_combined_smart_money_score
from .ml_model import predict_scores

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = DATA_DIR / "stock_data_cache.json"
RESULTS_FILE = DATA_DIR / "scan_results.json"
CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def _load_cache(max_age_hours: float) -> Optional[dict]:
    if CACHE_FILE.exists():
        age_h = (time.time() - CACHE_FILE.stat().st_mtime) / 3600
        if age_h < max_age_hours:
            logger.info("Using cached stock data (%.1fh old)", age_h)
            return json.loads(CACHE_FILE.read_text())
    return None


def _save_cache(data: dict):
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, default=str))


def fetch_stock_data(ticker: str, period: str = "1y") -> Optional[dict]:
    """Fetch info + history for a single ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        if not info.get("regularMarketPrice") and not info.get("currentPrice"):
            return None
        hist = t.history(period=period)
        if hist.empty:
            return None
        return {
            "info": {k: v for k, v in info.items() if not callable(v)},
            "history": hist.to_dict(orient="list"),
            "history_index": [str(d) for d in hist.index],
        }
    except Exception:
        logger.warning("Failed to fetch %s", ticker, exc_info=True)
        return None


def _reconstruct_hist(data: dict) -> pd.DataFrame:
    """Reconstruct history DataFrame from cached data."""
    hist = pd.DataFrame(data["history"])
    hist.index = pd.to_datetime(data["history_index"], utc=True)
    return hist


def _fetch_spy_hist(cache_hours: float, stock_data: dict) -> Optional[pd.DataFrame]:
    """Get SPY history for beta calculation."""
    if "SPY" in stock_data:
        return _reconstruct_hist(stock_data["SPY"])
    spy_data = fetch_stock_data("SPY", period="1y")
    if spy_data:
        stock_data["SPY"] = spy_data
        return _reconstruct_hist(spy_data)
    return None


def apply_filters(
    results: List[dict],
    filters: Optional[dict] = None,
    sector: Optional[str] = None,
    min_cap: Optional[float] = None,
    max_cap: Optional[float] = None,
    exclude_tickers: Optional[List[str]] = None,
    industries: Optional[List[str]] = None,
    strategy_filters: Optional[dict] = None,
) -> List[dict]:
    """Apply post-analysis filters to results."""
    if filters is None:
        filters = {}

    # Merge config filters with explicit overrides
    sectors = [sector] if sector else filters.get("sectors", [])
    inds = industries if industries else filters.get("industries", [])
    min_c = min_cap if min_cap is not None else filters.get("min_market_cap")
    max_c = max_cap if max_cap is not None else filters.get("max_market_cap")
    exclude = set(exclude_tickers or filters.get("exclude_tickers", []))

    filtered = results
    if sectors:
        sectors_lower = [s.lower() for s in sectors]
        filtered = [r for r in filtered if r.get("sector", "").lower() in sectors_lower]
    if inds:
        inds_lower = [i.lower() for i in inds]
        filtered = [r for r in filtered if r.get("industry", "").lower() in inds_lower]
    if min_c is not None:
        filtered = [r for r in filtered if (r.get("market_cap") or 0) >= min_c]
    if max_c is not None:
        filtered = [r for r in filtered if (r.get("market_cap") or 0) <= max_c]
    if exclude:
        exclude_upper = {t.upper() for t in exclude}
        filtered = [r for r in filtered if r["ticker"] not in exclude_upper]

    # Strategy-specific filters
    if strategy_filters:
        max_beta = strategy_filters.get("max_beta")
        if max_beta is not None:
            filtered = [r for r in filtered
                        if (r.get("risk") or {}).get("beta") is None
                        or (r.get("risk") or {}).get("beta", 999) <= max_beta]

        min_div = strategy_filters.get("min_dividend_yield")
        if min_div is not None:
            filtered = [r for r in filtered
                        if (r.get("info_cache", {}).get("dividendYield") or 0) >= min_div
                        or r.get("dividend_yield", 0) >= min_div]

        min_rev_growth = strategy_filters.get("min_revenue_growth")
        if min_rev_growth is not None:
            filtered = [r for r in filtered
                        if (r.get("growth") or {}).get("revenue_growth") is None
                        or ((r.get("growth") or {}).get("revenue_growth") or 0) >= min_rev_growth]

    return filtered


def analyze_single(
    ticker: str,
    data: dict,
    spy_hist: Optional[pd.DataFrame] = None,
    prev_data: Optional[dict] = None,
    regime: Optional[str] = None
) -> dict:
    """Run all scoring stages on a single stock.
    
    Args:
        ticker: Stock ticker symbol
        data: Stock data dict with info and history
        spy_hist: SPY history for beta calculation
        prev_data: Previous analysis result for sell signal comparison
    """
    info = data["info"]
    hist = _reconstruct_hist(data)

    fund = score_fundamentals(info)
    growth = score_growth(info)  # Compute growth first
    val = score_valuation(info, growth_score=growth.get("score"))  # Pass growth score to valuation
    tech = score_technicals(hist)
    risk = score_risk(hist, spy_hist)
    
    # Sentiment analysis — disabled across all strategies (rate-limited + too naive)
    # To re-enable: set sentiment weight > 0 in strategies.py and uncomment below
    # sentiment = analyze_sentiment(ticker)
    sentiment = {"score": 0, "details": "disabled"}

    momentum = compute_momentum(hist)

    # Compute sell signals
    prev_fund_score = None
    prev_signal = None
    if prev_data:
        prev_fund_score = (prev_data.get("fundamentals") or {}).get("score")
        prev_signal = (prev_data.get("momentum") or {}).get("entry_signal")
    
    sell_signals = compute_sell_signals(
        hist=hist,
        fundamentals_score=fund.get("score"),
        prev_fundamentals_score=prev_fund_score,
        current_signal=momentum.get("entry_signal"),
        prev_signal=prev_signal,
        resistance=momentum.get("resistance"),
        valuation_score=val.get("score"),
        risk_score=risk.get("score"),
        entry_price=None,  # Not tracking entry prices in screening mode
        stop_loss_pct=-15.0,
        adx=momentum.get("adx"),  # Pass ADX from momentum data
        regime=regime,  # Pass market regime for threshold adjustments
    )

    return {
        "ticker": ticker,
        "name": info.get("shortName", ticker),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
        "market_cap": info.get("marketCap"),
        "dividend_yield": info.get("dividendYield", 0) or 0,
        "fundamentals": fund,
        "valuation": val,
        "technicals": tech,
        "risk": risk,
        "growth": growth,
        "sentiment": sentiment,
        "momentum": momentum,
        "sell_signals": sell_signals,
    }


def run_scan(
    config: Optional[dict] = None,
    sector: Optional[str] = None,
    min_cap: Optional[float] = None,
    max_cap: Optional[float] = None,
    exclude_tickers: Optional[List[str]] = None,
    strategy: str = "balanced",
) -> dict:
    """Run the full pipeline. Returns {results: [...], ranked: [...], timestamp}."""
    if config is None:
        config = load_config()

    cache_hours = config.get("cache_hours", 24)
    weights = config.get("weights", {})
    thresholds = config.get("thresholds", {})
    filters = config.get("filters", {})
    top_n = config.get("top_n", 20)

    # Get strategy config
    strat = get_strategy(strategy)
    strat_filters = strat.get("filters", {})

    # Use strategy min_market_cap if higher than base threshold
    min_cap_threshold = float(strat_filters.get("min_market_cap", thresholds.get("min_market_cap", 2e9)))
    min_vol = float(thresholds.get("min_volume", 500000))

    tickers = get_sp500_tickers(cache_hours)
    logger.info("Scanning %d tickers with strategy '%s'...", len(tickers), strategy)

    # Try cache
    cached = _load_cache(cache_hours)
    stock_data = cached if cached else {}

    # Fetch missing
    missing = [t for t in tickers if t not in stock_data]
    if missing:
        logger.info("Fetching data for %d stocks...", len(missing))
        for i, ticker_sym in enumerate(missing):
            if i % 50 == 0 and i > 0:
                logger.info("Progress: %d/%d", i, len(missing))
            result = fetch_stock_data(ticker_sym)
            if result:
                stock_data[ticker_sym] = result
        _save_cache(stock_data)

    # Fetch SPY for beta and regime detection
    spy_hist = _fetch_spy_hist(cache_hours, stock_data)
    
    # Detect market regime
    regime_data = detect_market_regime(spy_hist) if spy_hist is not None else {}
    regime = regime_data.get("regime", "sideways")
    logger.info(f"Market regime detected: {regime.upper()} (confidence: {regime_data.get('confidence', 0):.0%})")

    # Load previous scan results for sell signal comparison
    # Uses the actual previous scan output (scores/signals) rather than re-analyzing
    prev_results_file = DATA_DIR / "prev_scan_results.json"
    prev_results_map = {}  # type: Dict[str, dict]
    if prev_results_file.exists():
        try:
            prev_scan = json.loads(prev_results_file.read_text())
            # Load from top (detailed) AND all_scores (lightweight, covers all 500+)
            for stock in prev_scan.get("top", []):
                ticker_sym = stock.get("ticker")
                if ticker_sym:
                    prev_results_map[ticker_sym] = {
                        "fundamentals": {"score": stock.get("fundamentals_pct")},
                        "momentum": {"entry_signal": stock.get("entry_signal")},
                    }
            for stock in prev_scan.get("all_scores", []):
                ticker_sym = stock.get("ticker")
                if ticker_sym and ticker_sym not in prev_results_map:
                    prev_results_map[ticker_sym] = {
                        "fundamentals": {"score": stock.get("fund_score")},
                        "momentum": {"entry_signal": stock.get("signal")},
                    }
        except Exception:
            logger.warning("Could not load previous results for sell signal comparison")

    # Analyze
    results = []
    for ticker_sym in tickers:
        if ticker_sym not in stock_data:
            continue
        data = stock_data[ticker_sym]
        info = data["info"]

        # Apply base thresholds
        cap = info.get("marketCap", 0) or 0
        vol = info.get("averageVolume", 0) or 0
        if cap < min_cap_threshold or vol < min_vol:
            continue

        try:
            prev_data = prev_results_map.get(ticker_sym)
            result = analyze_single(ticker_sym, data, spy_hist, prev_data, regime=regime)
            results.append(result)
        except Exception:
            logger.warning("Analysis failed for %s", ticker_sym, exc_info=True)

    logger.info("Analyzed %d stocks", len(results))

    # Apply filters (including strategy-specific)
    filtered = apply_filters(
        results,
        filters=filters,
        sector=sector,
        min_cap=min_cap,
        max_cap=max_cap,
        exclude_tickers=exclude_tickers,
        strategy_filters=strat_filters,
    )
    logger.info("After filtering: %d stocks", len(filtered))

    # Compute sector-relative scores
    sector_scores = compute_sector_relative_scores(results)

    # Score and rank (on filtered set), passing sector scores for sector-relative weighting
    ranked_df = compute_composite(filtered, weights, strategy=strategy, sector_scores=sector_scores, regime=regime)
    
    # --- ML Integration with Adaptive Weighting ---
    # Count daily snapshots to determine ML weight
    snapshot_dir = DATA_DIR / "daily_snapshots"
    snapshot_count = len(list(snapshot_dir.glob("*.json"))) if snapshot_dir.exists() else 0
    
    # Check if ML has been auto-disabled due to poor performance
    ml_weight_state_file = DATA_DIR / "ml_weight_state.json"
    ml_disabled = False
    if ml_weight_state_file.exists():
        try:
            ml_state = json.loads(ml_weight_state_file.read_text())
            if ml_state.get("ml_disabled"):
                ml_disabled = True
                logger.warning(f"⚠️ ML disabled: {ml_state.get('reason', 'Unknown reason')}")
        except Exception:
            pass
    
    # Adaptive ML weight based on training data availability
    if ml_disabled:
        ml_weight = 0.0
        logger.info("ML weight = 0% (auto-disabled due to poor performance)")
    elif snapshot_count < 10:
        ml_weight = 0.0  # Not enough data, don't use ML
        logger.info(f"ML integration: {snapshot_count} snapshots available, ML weight = 0% (insufficient data)")
    elif snapshot_count < 30:
        ml_weight = 0.10  # 10-30 days: 10% ML
        logger.info(f"ML integration: {snapshot_count} snapshots available, ML weight = 10%")
    elif snapshot_count < 60:
        ml_weight = 0.20  # 30-60 days: 20% ML
        logger.info(f"ML integration: {snapshot_count} snapshots available, ML weight = 20%")
    else:
        ml_weight = 0.30  # 60+ days: 30% ML
        logger.info(f"ML integration: {snapshot_count} snapshots available, ML weight = 30%")
    
    # Apply ML scoring if model exists and weight > 0
    ml_scores_map = {}
    if ml_weight > 0:
        try:
            # Get ML predictions for top stocks
            ml_predictions = predict_scores()
            if ml_predictions and not ml_predictions[0].get("error"):
                ml_scores_map = {p["ticker"]: p for p in ml_predictions}
                logger.info(f"ML predictions obtained for {len(ml_scores_map)} stocks")
        except Exception as e:
            logger.warning(f"ML prediction failed: {e}")
            ml_weight = 0.0  # Fall back to no ML if prediction fails

    # Merge details
    detail_map = {r["ticker"]: r for r in filtered}
    ranked = []
    for _, row in ranked_df.head(top_n).iterrows():
        tkr = row["ticker"]
        detail = detail_map[tkr]
        sr = sector_scores.get(tkr, {})
        sell_sig = detail.get("sell_signals") or {}
        
        # Get base composite score
        base_composite = float(row["composite"])
        
        # Blend with ML score if available
        ml_data = ml_scores_map.get(tkr)
        if ml_data and ml_weight > 0:
            ml_score = ml_data.get("ml_score", 50)  # ML score is 0-100
            # Final score = base * (1 - weight) + ml * weight
            final_composite = base_composite * (1 - ml_weight) + ml_score * ml_weight
            ml_signal = ml_data.get("consensus_signal", "N/A")
        else:
            final_composite = base_composite
            ml_score = None
            ml_signal = None
        
        ranked.append({
            "rank": int(row["rank"]),
            "ticker": tkr,
            "name": detail["name"],
            "sector": detail["sector"],
            "industry": detail.get("industry", "Unknown"),
            "market_cap": detail.get("market_cap"),
            "composite_score": round(final_composite, 2),
            "base_score": round(base_composite, 2),
            "ml_score": round(ml_score, 2) if ml_score is not None else None,
            "ml_signal": ml_signal,
            "ml_weight": round(ml_weight, 2),
            "fundamentals_pct": round(float(row["fund_pct"]), 2) if pd.notna(row["fund_pct"]) else None,
            "valuation_pct": round(float(row["val_pct"]), 2) if pd.notna(row["val_pct"]) else None,
            "technicals_pct": round(float(row["tech_pct"]), 2) if pd.notna(row["tech_pct"]) else None,
            "risk_pct": round(float(row["risk_pct"]), 2) if pd.notna(row["risk_pct"]) else None,
            "growth_pct": round(float(row["growth_pct"]), 2) if pd.notna(row["growth_pct"]) else None,
            "sentiment_score": (detail.get("sentiment") or {}).get("score"),
            "sentiment_pct": round(float(row["sent_pct"]), 2) if pd.notna(row["sent_pct"]) else None,
            "sector_rank": sr.get("sector_rank"),
            "sector_size": sr.get("sector_size"),
            "sector_composite": sr.get("sector_composite"),
            "entry_signal": (detail.get("momentum") or {}).get("entry_signal", "HOLD"),
            "entry_score": (detail.get("momentum") or {}).get("entry_score"),
            "sell_signal": sell_sig.get("sell_signal", "N/A"),
            "sell_urgency": sell_sig.get("urgency", "none"),
            "sell_reasons": sell_sig.get("sell_reasons", []),
            # Price data (needed for validation + rebalance)
            "current_price": sell_sig.get("current_price"),
            # Technical features (needed for ML predictions)
            "rsi": sell_sig.get("rsi"),
            "macd_histogram": (detail.get("technicals") or {}).get("macd_histogram"),
            "adx": (detail.get("momentum") or {}).get("adx"),
            "volatility": (detail.get("risk") or {}).get("volatility"),
            "beta": (detail.get("risk") or {}).get("beta"),
            "volume_trend": (detail.get("technicals") or {}).get("volume_trend"),
            "ma50": (detail.get("technicals") or {}).get("ma50"),
            "ma200": (detail.get("technicals") or {}).get("ma200"),
            "above_ma50": (detail.get("technicals") or {}).get("above_ma50"),
            "above_ma200": (detail.get("technicals") or {}).get("above_ma200"),
        })

    # --- Smart money signals (analyst revisions + insider trading) for top N only ---
    # Only fetch for top_n to avoid 500 yfinance API calls
    logger.info("Fetching smart money data for top %d stocks...", len(ranked))
    for stock in ranked:
        try:
            ticker_obj = yf.Ticker(stock["ticker"])
            sm = get_combined_smart_money_score(ticker_obj)
            stock["smart_money_score"] = sm["score"]
            stock["analyst_score"] = sm["analyst_score"]
            stock["insider_score"] = sm["insider_score"]
            stock["smart_money_signals"] = sm.get("signals", [])
        except Exception:
            stock["smart_money_score"] = 50
            stock["analyst_score"] = 50
            stock["insider_score"] = 50
            stock["smart_money_signals"] = []

    # --- Apply smart money bonus to composite score ---
    sm_cfg = strat.get("smart_money_bonus", {})
    if sm_cfg.get("enabled", False):
        for stock in ranked:
            sm_score = stock.get("smart_money_score", 50)
            bonus = 0
            if sm_score > 70:
                bonus = sm_cfg.get("strong_positive", 5)
            elif sm_score > 60:
                bonus = sm_cfg.get("moderate_positive", 2)
            elif sm_score < 30:
                bonus = sm_cfg.get("strong_negative", -5)
            elif sm_score < 40:
                bonus = sm_cfg.get("moderate_negative", -2)
            if bonus != 0:
                stock["composite_score"] = max(0, stock.get("composite_score", 0) + bonus)
                stock["smart_money_bonus"] = bonus

    # --- Add data freshness ---
    for stock in ranked:
        freshness_label, age_days = check_freshness(stock["ticker"])
        stock["data_freshness"] = freshness_label
        stock["data_age_days"] = age_days

    # --- Apply earnings guard ---
    ranked = apply_earnings_guard(ranked)

    # --- Update streak tracking ---
    top20_tickers = [stock["ticker"] for stock in ranked[:20]]
    current_date = time.strftime("%Y-%m-%d")
    update_streaks(top20_tickers, current_date)
    
    # --- Add consecutive_days to results ---
    ranked = add_streaks_to_results(ranked)

    # --- Removed auto-upgrade logic (was upgrading all top-20 >75 to BUY, killing signal diversity) ---
    # Entry signals now come purely from momentum analysis; composite score is a separate dimension.

    # --- Sanity checks on output ---
    sanity_warnings = []
    if ranked:
        signal_counts = {}
        for s in ranked:
            sig = s.get("entry_signal", "N/A")
            signal_counts[sig] = signal_counts.get(sig, 0) + 1
        total = len(ranked)
        for sig, count in signal_counts.items():
            if count / total > 0.80:
                sanity_warnings.append(f"Signal imbalance: {count}/{total} ({count/total*100:.0f}%) are {sig}")
        
        scores = [s.get("composite_score", 0) for s in ranked if s.get("composite_score")]
        if scores:
            score_range = max(scores) - min(scores)
            if score_range < 5:
                sanity_warnings.append(f"Score clustering: range only {score_range:.1f} (all scores too similar)")
            avg_score = sum(scores) / len(scores)
            if avg_score > 90:
                sanity_warnings.append(f"Score inflation: avg {avg_score:.1f} (too high, scoring may be broken)")
        
        # Check for duplicate tickers
        tickers = [s.get("ticker") for s in ranked]
        if len(tickers) != len(set(tickers)):
            sanity_warnings.append("Duplicate tickers in results!")
    
    if sanity_warnings:
        for w in sanity_warnings:
            logger.warning("SANITY CHECK: %s", w)

    # Build lightweight all_scores for full-universe prev comparison (covers all 500+ stocks)
    # This lets next scan detect signal changes for stocks outside top-N
    results_by_ticker = {r["ticker"]: r for r in filtered if "ticker" in r}
    all_scores = []
    for _, row in ranked_df.iterrows():
        tkr = row.get("ticker")
        detail = results_by_ticker.get(tkr, {})
        all_scores.append({
            "ticker": tkr,
            "composite": round(float(row.get("composite", 0)), 2),
            "fund_score": round(float(row.get("fund_pct", 0)), 2) if pd.notna(row.get("fund_pct")) else None,
            "signal": (detail.get("momentum") or {}).get("entry_signal", "HOLD"),
        })

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "strategy": strategy,
        "market_regime": regime_data,
        "stocks_analyzed": len(results),
        "stocks_after_filter": len(filtered),
        "sanity_warnings": sanity_warnings,
        "top": ranked,
        "all_scores": all_scores,
    }

    # Rotate: current → previous (BEFORE saving new results)
    PREV_RESULTS_FILE = DATA_DIR / "prev_scan_results.json"
    if RESULTS_FILE.exists():
        try:
            import shutil
            shutil.copy2(RESULTS_FILE, PREV_RESULTS_FILE)
            logger.info("Rotated scan results → prev_scan_results.json")
        except Exception as e:
            logger.warning("Failed to rotate scan results: %s", e)

    # Save results
    DATA_DIR.mkdir(exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(output, indent=2, default=str))
    
    # Also save daily snapshot
    snapshot_dir = DATA_DIR / "daily_snapshots"
    snapshot_dir.mkdir(exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    snapshot_file = snapshot_dir / f"{today}.json"
    if not snapshot_file.exists():
        snapshot_file.write_text(json.dumps(output, indent=2, default=str))
        logger.info("Saved daily snapshot: %s", snapshot_file)

    return output


def get_stock_detail(ticker: str, config: Optional[dict] = None) -> Optional[dict]:
    """Get detailed breakdown for a single stock."""
    if config is None:
        config = load_config()

    cache_hours = config.get("cache_hours", 24)
    cached = _load_cache(cache_hours)

    ticker = ticker.upper()
    stock_data = cached or {}
    data = stock_data.get(ticker)

    if not data:
        data = fetch_stock_data(ticker)
        if not data:
            return None

    spy_hist = _fetch_spy_hist(cache_hours, stock_data)
    
    # Detect regime for single stock analysis
    regime_data = detect_market_regime(spy_hist) if spy_hist is not None else {}
    regime = regime_data.get("regime", "sideways")
    
    return analyze_single(ticker, data, spy_hist, regime=regime)


def get_all_sectors(config: Optional[dict] = None) -> Dict[str, int]:
    """Return dict of sector → stock count from cached data."""
    if config is None:
        config = load_config()

    cached = _load_cache(config.get("cache_hours", 24))
    if not cached:
        return {}

    sectors = {}  # type: Dict[str, int]
    for data in cached.values():
        sector = data.get("info", {}).get("sector", "Unknown")
        sectors[sector] = sectors.get(sector, 0) + 1
    return dict(sorted(sectors.items()))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run_scan()
    print(f"\n{'='*60}")
    print(f"Stock Screener Results — {result['timestamp']}")
    print(f"Strategy: {result['strategy']}")
    print(f"Analyzed {result['stocks_analyzed']} stocks")
    print(f"{'='*60}\n")
    for s in result["top"]:
        print(f"  #{s['rank']:>2}  {s['ticker']:<6} {s['name']:<30} Score: {s['composite_score']:>6.2f}")
    print()
