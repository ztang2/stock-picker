"""Orchestrate the full stock screening pipeline."""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd
import yaml
import yfinance as yf

from .universe import get_sp500_tickers, get_universe_tickers
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
from .sentiment import score_analyst_sentiment
from .market_regime import detect_market_regime, detect_geopolitical_events
from .insider import get_combined_smart_money_score
from .ml_model import predict_scores
from .alpha158_predictor import predict_for_stocks as alpha158_predict

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
    hist = hist.dropna(subset=["Close"])
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

    # Hard filter: exclude stocks with severe revenue decline (value trap protection)
    # Revenue shrinking >10% is a red flag regardless of valuation
    before_count = len(filtered)
    filtered = [r for r in filtered
                if (r.get("growth") or {}).get("revenue_growth") is None
                or ((r.get("growth") or {}).get("revenue_growth") or 0) >= -0.10]
    dropped = before_count - len(filtered)
    if dropped > 0:
        logger.info("Value trap filter: removed %d stocks with revenue decline >10%%", dropped)

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
    
    sentiment = score_analyst_sentiment(info)

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
    # Auto-heal cache before scanning
    try:
        from .cache_health import heal_cache
        heal_report = heal_cache()
        logger.info("Cache heal: %s", heal_report)
    except Exception as e:
        logger.warning("Cache heal failed: %s", e)

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

    tickers = get_universe_tickers(cache_hours)
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
            # Rate limit protection: pause every 20 tickers to avoid Yahoo ban
            if (i + 1) % 20 == 0 and i < len(missing) - 1:
                time.sleep(2)
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
            for stock in prev_scan.get("top", prev_scan.get("stocks", [])):
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
                        "fundamentals": {"score": stock.get("fundamentals_pct") or stock.get("fund_score")},
                        "momentum": {"entry_signal": stock.get("entry_signal") or stock.get("signal")},
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

    # Detect geopolitical events and get industry adjustments
    from .market_regime import get_geopolitical_adjustments
    geo_adjustments = get_geopolitical_adjustments(regime_data)
    if geo_adjustments:
        logger.info(f"Geopolitical adjustments active: {len(geo_adjustments)} industries affected")

    # Score and rank (on filtered set), passing sector scores for sector-relative weighting
    ranked_df = compute_composite(filtered, weights, strategy=strategy, sector_scores=sector_scores, regime=regime, geo_adjustments=geo_adjustments)
    
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
    
    # Adaptive ML weight based on MODEL ACCURACY, not just data availability
    # ML must EARN its weight by proving accuracy > 55%
    ml_accuracy = None
    try:
        # Check both possible locations for ML metrics
        for ml_metrics_path in [DATA_DIR / "ml_metrics.json", DATA_DIR / "ml" / "metrics.json"]:
            if ml_metrics_path.exists():
                ml_meta = json.loads(ml_metrics_path.read_text())
                ml_accuracy = ml_meta.get("accuracy")
                if ml_accuracy is not None:
                    break
    except Exception:
        pass
    
    if ml_disabled:
        ml_weight = 0.0
        logger.info("ML weight = 0% (auto-disabled due to poor performance)")
    elif snapshot_count < 10:
        ml_weight = 0.0
        logger.info(f"ML weight = 0% ({snapshot_count} snapshots, insufficient data)")
    elif ml_accuracy is not None and ml_accuracy < 0.55:
        ml_weight = 0.0  # Model not good enough yet
        logger.info(f"ML weight = 0% (accuracy {ml_accuracy:.1%} < 55% threshold)")
    elif ml_accuracy is not None and ml_accuracy < 0.60:
        ml_weight = 0.10  # Barely useful: 10%
        logger.info(f"ML weight = 10% (accuracy {ml_accuracy:.1%})")
    elif ml_accuracy is not None and ml_accuracy < 0.65:
        ml_weight = 0.20  # Decent: 20%
        logger.info(f"ML weight = 20% (accuracy {ml_accuracy:.1%})")
    else:
        ml_weight = 0.30  # Strong: 30%
        logger.info(f"ML weight = 30% (accuracy {ml_accuracy})")
    
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

    # --- Alpha158 ML Integration (Qlib methodology) ---
    alpha158_map = {}
    alpha158_weight = 0.0
    try:
        alpha158_metrics_file = DATA_DIR / "alpha158_models" / "metrics.json"
        if alpha158_metrics_file.exists():
            a158_meta = json.loads(alpha158_metrics_file.read_text())
            a158_ic = a158_meta.get("ensemble_ic", 0)
            # IC-based weight: IC > 0.03 = 10%, IC > 0.05 = 15%, IC > 0.08 = 20%
            if a158_ic > 0.08:
                alpha158_weight = 0.20
            elif a158_ic > 0.05:
                alpha158_weight = 0.15
            elif a158_ic > 0.03:
                alpha158_weight = 0.10
            else:
                alpha158_weight = 0.0
            logger.info(f"Alpha158 IC: {a158_ic:.4f} → weight: {alpha158_weight:.0%}")
            
            if alpha158_weight > 0:
                # Only predict for top stocks to save time (not all 800)
                top_tickers = [row["ticker"] for _, row in ranked_df.head(min(top_n * 3, 100)).iterrows()]
                a158_preds = alpha158_predict(tickers=top_tickers)
                if a158_preds and not a158_preds[0].get("error"):
                    alpha158_map = {p["ticker"]: p for p in a158_preds}
                    logger.info(f"Alpha158 predictions for {len(alpha158_map)} stocks")
    except Exception as e:
        logger.warning(f"Alpha158 prediction failed: {e}")
        alpha158_weight = 0.0

    # Merge details
    detail_map = {r["ticker"]: r for r in filtered}
    # Sector-capped selection: max 4 per sector in top N to prevent concentration
    MAX_PER_SECTOR = 4
    sector_counts = {}
    selected_tickers = []
    for _, row in ranked_df.iterrows():
        if len(selected_tickers) >= top_n:
            break
        tkr = row["ticker"]
        sector = detail_map.get(tkr, {}).get("sector", "Unknown")
        if sector_counts.get(sector, 0) >= MAX_PER_SECTOR:
            continue
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        selected_tickers.append(tkr)
    
    ranked = []
    for _, row in ranked_df[ranked_df["ticker"].isin(selected_tickers)].iterrows():
        tkr = row["ticker"]
        detail = detail_map[tkr]
        sr = sector_scores.get(tkr, {})
        sell_sig = detail.get("sell_signals") or {}
        
        # Get base composite score
        base_composite = float(row["composite"])
        
        # Blend with old ML score if available
        ml_data = ml_scores_map.get(tkr)
        if ml_data and ml_weight > 0:
            ml_score = ml_data.get("ml_score", 50)
            final_composite = base_composite * (1 - ml_weight) + ml_score * ml_weight
            ml_signal = ml_data.get("consensus_signal", "N/A")
        else:
            final_composite = base_composite
            ml_score = None
            ml_signal = None
        
        # Blend with Alpha158 score (Qlib methodology)
        a158_data = alpha158_map.get(tkr)
        a158_score = None
        if a158_data and alpha158_weight > 0:
            # Alpha158 predicts excess return (%). Convert to 0-100 scale:
            # -5% → 25, 0% → 50, +5% → 75 (linear mapping)
            raw_pred = a158_data.get("predicted_excess_return", 0)
            a158_score = max(0, min(100, 50 + raw_pred * 5))  # 1% excess = 5 points
            final_composite = final_composite * (1 - alpha158_weight) + a158_score * alpha158_weight
        
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
            "alpha158_score": round(a158_score, 1) if a158_score is not None else None,
            "alpha158_pred": a158_data.get("predicted_excess_return") if a158_data else None,
            "alpha158_weight": round(alpha158_weight, 2),
            "fundamentals_pct": round(float(row["fund_pct"]), 2) if pd.notna(row["fund_pct"]) else None,
            "valuation_pct": round(float(row["val_pct"]), 2) if pd.notna(row["val_pct"]) else None,
            "technicals_pct": round(float(row["tech_pct"]), 2) if pd.notna(row["tech_pct"]) else None,
            "risk_pct": round(float(row["risk_pct"]), 2) if pd.notna(row["risk_pct"]) else None,
            "growth_pct": round(float(row["growth_pct"]), 2) if pd.notna(row["growth_pct"]) else None,
            "sentiment": detail.get("sentiment"),
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

    # --- DCF & Comps bonus for top N (avoid running on all 500+) ---
    # Cache S&P 500 tickers for midcap penalty check
    from .universe import get_sp500_tickers
    _sp500_set = set(get_sp500_tickers())
    logger.info("Running DCF & comps analysis for top %d stocks...", len(ranked))
    dcf_comps_start = time.time()
    
    from .dcf_valuation import run_dcf
    from .comps_analysis import run_comps
    
    def _fetch_dcf_comps(ticker: str):
        dcf_result = None
        comps_result = None
        try:
            dcf_result = run_dcf(ticker)
        except Exception:
            pass
        try:
            comps_result = run_comps(ticker, max_peers=10)
        except Exception:
            pass
        return ticker, dcf_result, comps_result
    
    dcf_comps_map = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_dcf_comps, s["ticker"]): s["ticker"] for s in ranked}
        for future in as_completed(futures):
            ticker_sym, dcf_r, comps_r = future.result()
            dcf_comps_map[ticker_sym] = (dcf_r, comps_r)
    
    for stock in ranked:
        tkr = stock["ticker"]
        dcf_r, comps_r = dcf_comps_map.get(tkr, (None, None))
        
        dcf_bonus = 0
        if dcf_r and "error" not in dcf_r:
            mos = dcf_r.get("margin_of_safety", 0)
            confidence = dcf_r.get("confidence", "HIGH")
            stock["dcf_intrinsic"] = dcf_r.get("intrinsic_value")
            stock["dcf_margin_of_safety"] = round(mos, 2)
            stock["dcf_verdict"] = dcf_r.get("verdict")
            stock["dcf_confidence"] = confidence
            # Only apply bonus if confidence is HIGH or MEDIUM
            if confidence != "LOW":
                if mos > 30:
                    dcf_bonus = 4
                elif mos > 15:
                    dcf_bonus = 2
                elif mos < -50:
                    dcf_bonus = -3
                elif mos < -30:
                    dcf_bonus = -1
        
        comps_bonus = 0
        if comps_r and "error" not in comps_r:
            cs = comps_r.get("comps_score", 50)
            stock["comps_score"] = round(cs, 1)
            stock["comps_verdict"] = comps_r.get("verdict")
            # Bonus based on relative valuation
            if cs > 70:
                comps_bonus = 3
            elif cs > 55:
                comps_bonus = 1
            elif cs < 30:
                comps_bonus = -3
            elif cs < 40:
                comps_bonus = -1
        
        total_val_bonus = dcf_bonus + comps_bonus
        if total_val_bonus != 0:
            stock["composite_score"] = max(0, stock.get("composite_score", 0) + total_val_bonus)
            stock["valuation_bonus"] = total_val_bonus

        # --- Risk adjustments ---

        # 1. MidCap volatility discount: S&P 400 stocks get -2 penalty (higher risk)
        if tkr not in _sp500_set:
            stock["composite_score"] = max(0, stock.get("composite_score", 0) - 2)
            stock["midcap_penalty"] = -2

        # 2. Momentum crash filter: use price vs MA50 as proxy for recent drawdown
        price = stock.get("current_price", 0)
        ma50 = stock.get("ma50", 0)
        if price and ma50 and ma50 > 0:
            drawdown_from_ma50 = (price / ma50 - 1) * 100
            stock["drawdown_from_ma50"] = round(drawdown_from_ma50, 1)
            if drawdown_from_ma50 < -20:
                stock["entry_signal"] = "WATCH"
                stock["momentum_warning"] = f"Price {drawdown_from_ma50:.1f}% below MA50 — possible falling knife"

        # 3. LOW confidence DCF penalty: slight -1 instead of neutral 0
        if dcf_r and "error" not in dcf_r and dcf_r.get("confidence") == "LOW":
            stock["composite_score"] = max(0, stock.get("composite_score", 0) - 1)
            stock["dcf_low_penalty"] = -1

    logger.info("DCF & comps analysis completed in %.1fs", time.time() - dcf_comps_start)

    # --- Quality scores (Piotroski F-Score + Altman Z-Score) for top N ---
    logger.info("Computing quality scores for top %d stocks...", len(ranked))
    quality_start = time.time()
    
    from .quality_scores import compute_quality_scores
    
    def _fetch_quality(ticker: str):
        try:
            return ticker, compute_quality_scores(ticker)
        except Exception:
            return ticker, None
    
    quality_map = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_quality, s["ticker"]): s["ticker"] for s in ranked}
        for future in as_completed(futures):
            tkr_q, q_result = future.result()
            if q_result:
                quality_map[tkr_q] = q_result
    
    for stock in ranked:
        tkr = stock["ticker"]
        q = quality_map.get(tkr)
        if q:
            p = q.get("piotroski", {})
            a = q.get("altman", {})
            stock["piotroski_score"] = p.get("score")
            stock["piotroski_grade"] = p.get("grade")
            stock["altman_z_score"] = a.get("score")
            stock["altman_zone"] = a.get("zone")
            stock["quality_score"] = q.get("quality_score")
            
            # Quality bonus/penalty
            quality_bonus = 0
            ps = p.get("score")
            az = a.get("score")
            
            # Piotroski 8-9 = strong company, 0-3 = weak
            if ps is not None:
                if ps >= 8:
                    quality_bonus += 2
                elif ps >= 6:
                    quality_bonus += 1
                elif ps <= 3:
                    quality_bonus -= 2
                elif ps <= 4:
                    quality_bonus -= 1
            
            # Altman: distress zone = big penalty
            if az is not None:
                if az < 1.8:
                    quality_bonus -= 3
                elif az > 5.0:
                    quality_bonus += 1
            
            # Earnings decline penalty (separate from quality)
            eg = stock.get("earnings_growth") or (stock.get("growth", {}) or {}).get("earnings_growth")
            if eg is not None and eg < -0.3:  # earnings dropped >30%
                quality_bonus -= 2
                stock["earnings_decline_flag"] = f"earnings_growth_{eg*100:.0f}%"
            elif eg is not None and eg < -0.15:  # earnings dropped >15%
                quality_bonus -= 1
                stock["earnings_decline_flag"] = f"earnings_growth_{eg*100:.0f}%"

            if quality_bonus != 0:
                stock["composite_score"] = max(0, stock.get("composite_score", 0) + quality_bonus)
                stock["quality_bonus"] = quality_bonus
    
    logger.info("Quality scores completed in %.1fs", time.time() - quality_start)

    # --- Insider selling penalty + Short interest penalty (top N only) ---
    # Fetch insider data for ranked stocks and penalize heavy selling
    logger.info("Checking insider selling & short interest for top %d stocks...", len(ranked))
    insider_start = time.time()

    def _fetch_insider_short(ticker: str):
        """Fetch 2026 insider transactions and short interest."""
        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}
            short_pct = info.get("shortPercentOfFloat", 0) or 0

            # Insider transactions (2026 only)
            insider_sell_value = 0
            insider_buy_value = 0
            insider_sells = 0
            insider_buys = 0
            ins = tk.insider_transactions
            if ins is not None and not ins.empty:
                recent = ins[ins['Start Date'] >= '2026-01-01']
                for _, row in recent.iterrows():
                    text = str(row.get("Text", "")).lower()
                    value = abs(row.get("Value", 0) or 0)
                    if "purchase" in text or "buy" in text:
                        insider_buys += 1
                        insider_buy_value += value
                    elif "sale" in text:
                        insider_sells += 1
                        insider_sell_value += value

            return ticker, {
                "short_pct": short_pct,
                "insider_sell_value": insider_sell_value,
                "insider_buy_value": insider_buy_value,
                "insider_sells": insider_sells,
                "insider_buys": insider_buys,
            }
        except Exception:
            return ticker, None

    insider_results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_insider_short, s["ticker"]): s["ticker"] for s in ranked}
        for future in as_completed(futures):
            ticker, data = future.result()
            insider_results[ticker] = data

    for stock in ranked:
        idata = insider_results.get(stock["ticker"])
        if not idata:
            continue

        penalty = 0
        flags = []

        # Insider selling penalty
        sell_val = idata["insider_sell_value"]
        buy_val = idata["insider_buy_value"]
        buys = idata["insider_buys"]

        if sell_val > 10_000_000 and buys == 0:
            penalty -= 3
            flags.append(f"insider_sell_critical_${sell_val/1e6:.0f}M")
        elif sell_val > 5_000_000 and buys == 0:
            penalty -= 2
            flags.append(f"insider_sell_high_${sell_val/1e6:.0f}M")
        elif sell_val > 1_000_000 and buys == 0:
            penalty -= 1
            flags.append(f"insider_sell_${sell_val/1e6:.1f}M")

        # Insider buying bonus
        if buy_val > 1_000_000:
            penalty += 2
            flags.append(f"insider_buy_${buy_val/1e6:.1f}M")
        elif buy_val > 500_000 and buys > 0:
            penalty += 1
            flags.append(f"insider_buy_${buy_val/1e3:.0f}K")

        # Short interest penalty
        short_pct = idata["short_pct"]
        if short_pct and short_pct > 0.15:  # >15%
            penalty -= 2
            flags.append(f"short_{short_pct*100:.1f}%")
        elif short_pct and short_pct > 0.10:  # >10%
            penalty -= 1
            flags.append(f"short_{short_pct*100:.1f}%")

        if penalty != 0:
            stock["composite_score"] = max(0, stock.get("composite_score", 0) + penalty)
            stock["insider_short_penalty"] = penalty
            stock["insider_short_flags"] = flags

        stock["insider_sell_value"] = sell_val
        stock["insider_buy_value"] = buy_val
        stock["insider_sells_2026"] = idata["insider_sells"]
        stock["insider_buys_2026"] = buys
        stock["short_pct_float"] = short_pct

    logger.info("Insider/short check completed in %.1fs", time.time() - insider_start)

    # --- Smart money signals (analyst revisions + insider trading) for top N only ---
    # Only fetch for top_n to avoid 500 yfinance API calls
    # Parallelized: each stock's 4 yfinance calls are I/O-bound and independent
    logger.info("Fetching smart money data for top %d stocks (parallel)...", len(ranked))
    sm_start = time.time()

    def _fetch_smart_money(ticker: str):
        try:
            ticker_obj = yf.Ticker(ticker)
            sm = get_combined_smart_money_score(ticker_obj)
            return ticker, sm
        except Exception:
            return ticker, None

    sm_results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_smart_money, s["ticker"]): s["ticker"] for s in ranked}
        for future in as_completed(futures):
            ticker, sm = future.result()
            sm_results[ticker] = sm

    for stock in ranked:
        sm = sm_results.get(stock["ticker"])
        if sm:
            stock["smart_money_score"] = sm["score"]
            stock["analyst_score"] = sm["analyst_score"]
            stock["insider_score"] = sm["insider_score"]
            stock["smart_money_signals"] = sm.get("signals", [])
        else:
            stock["smart_money_score"] = 50
            stock["analyst_score"] = 50
            stock["insider_score"] = 50
            stock["smart_money_signals"] = []

    logger.info("Smart money fetch completed in %.1fs", time.time() - sm_start)

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

    # --- Re-sort by final composite_score after all bonuses ---
    # Smart money bonus and earnings guard modify scores after initial ranking
    ranked.sort(key=lambda s: s.get("composite_score", 0), reverse=True)
    for i, stock in enumerate(ranked):
        stock["rank"] = i + 1

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

    # Build full all_scores for complete universe data (covers all 800+ stocks)
    # Stores complete scores for every analyzed stock — enables full Scanner view
    results_by_ticker = {r["ticker"]: r for r in filtered if "ticker" in r}
    all_scores = []
    for idx, row in ranked_df.iterrows():
        tkr = row.get("ticker")
        detail = results_by_ticker.get(tkr, {})
        momentum = detail.get("momentum") or {}
        technicals = detail.get("technicals") or {}
        sell = detail.get("sell_signals") or {}
        fund = detail.get("fundamentals") or {}
        val = detail.get("valuation") or {}
        risk_d = detail.get("risk") or {}
        growth_d = detail.get("growth") or {}
        sent = detail.get("sentiment") or {}
        all_scores.append({
            "ticker": tkr,
            "name": detail.get("name", ""),
            "sector": detail.get("sector", ""),
            "industry": detail.get("industry", ""),
            "composite_score": round(float(row.get("composite", 0)), 2),
            "rank": int(idx + 1) if isinstance(idx, (int, float)) else 0,
            "fundamentals_pct": round(float(row.get("fund_pct", 0)), 2) if pd.notna(row.get("fund_pct")) else 0,
            "valuation_pct": round(float(row.get("val_pct", 0)), 2) if pd.notna(row.get("val_pct")) else 0,
            "technicals_pct": round(float(row.get("tech_pct", 0)), 2) if pd.notna(row.get("tech_pct")) else 0,
            "risk_pct": round(float(row.get("risk_pct", 0)), 2) if pd.notna(row.get("risk_pct")) else 0,
            "growth_pct": round(float(row.get("growth_pct", 0)), 2) if pd.notna(row.get("growth_pct")) else 0,
            "entry_signal": momentum.get("entry_signal", "HOLD"),
            "current_price": technicals.get("price") or detail.get("current_price"),
            "rsi": technicals.get("rsi"),
            "ma50": technicals.get("ma50"),
            "ma200": technicals.get("ma200"),
            "market_cap": detail.get("market_cap"),
            "pe_ratio": (val.get("pe_ratio")),
            "dividend_yield": detail.get("dividend_yield"),
            "beta": (risk_d.get("beta")),
            "volatility": (risk_d.get("volatility")),
            "revenue_growth": (fund.get("revenue_growth")),
            "profit_margin": (fund.get("profit_margin")),
            "sentiment_score": sent.get("score"),
        })

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "strategy": strategy,
        "market_regime": regime_data,
        "geopolitical_events": detect_geopolitical_events(regime_data) if regime_data else [],
        "geo_adjustments": geo_adjustments if geo_adjustments else {},
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

    # Save results (sanitize NaN/Infinity for JSON compliance)
    def _sanitize(obj):
        import math
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        elif isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        return obj

    DATA_DIR.mkdir(exist_ok=True)
    output = _sanitize(output)
    RESULTS_FILE.write_text(json.dumps(output, indent=2, default=str))
    
    # Also save daily snapshot
    snapshot_dir = DATA_DIR / "daily_snapshots"
    snapshot_dir.mkdir(exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    snapshot_file = snapshot_dir / f"{today}.json"
    if not snapshot_file.exists():
        snapshot_file.write_text(json.dumps(output, indent=2, default=str))
        logger.info("Saved daily snapshot: %s", snapshot_file)
    
    # Save momentum radar snapshot for tracking
    try:
        from .early_momentum import scan_top_momentum
        momentum_dir = DATA_DIR / "momentum_snapshots"
        momentum_dir.mkdir(exist_ok=True)
        momentum_file = momentum_dir / f"{today}.json"
        if not momentum_file.exists():
            momentum_data = scan_top_momentum(20)
            momentum_file.write_text(json.dumps(momentum_data, indent=2, default=str))
            logger.info("Saved momentum snapshot: %s (%d stocks)", momentum_file, len(momentum_data))
    except Exception as e:
        logger.warning("Momentum snapshot failed: %s", e)

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
