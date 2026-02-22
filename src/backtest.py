"""Backtesting engine: evaluate historical performance of top scored picks."""

import json
import logging
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

from .pipeline import load_config, analyze_single, _reconstruct_hist, DATA_DIR
from .universe import get_sp500_tickers
from .scorer import compute_composite

logger = logging.getLogger(__name__)

BACKTEST_FILE = DATA_DIR / "backtest_results.json"
ROLLING_BACKTEST_FILE = DATA_DIR / "rolling_backtest.json"

_price_cache: Dict[str, pd.DataFrame] = {}

# Rolling backtest progress tracking
_rolling_status: Dict[str, object] = {
    "running": False,
    "progress": 0,
    "total": 0,
    "message": "",
}


def _get_hist(ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch historical data for a ticker between dates."""
    key = "%s_%s_%s" % (ticker, start, end)
    if key in _price_cache:
        return _price_cache[key]
    try:
        t = yf.Ticker(ticker)
        hist = t.history(start=start, end=end)
        if hist is not None and not hist.empty:
            _price_cache[key] = hist
            return hist
    except Exception:
        logger.warning("Failed to fetch history for %s", ticker, exc_info=True)
    return None


def _get_price_at(ticker: str, date: str, days_tolerance: int = 5) -> Optional[float]:
    """Get closing price near a date."""
    dt = datetime.strptime(date, "%Y-%m-%d")
    start = (dt - timedelta(days=days_tolerance)).strftime("%Y-%m-%d")
    end = (dt + timedelta(days=days_tolerance)).strftime("%Y-%m-%d")
    hist = _get_hist(ticker, start, end)
    if hist is None or hist.empty:
        return None
    # Find closest date — normalize timezone
    target = pd.Timestamp(date)
    if hist.index.tz is not None:
        target = target.tz_localize(hist.index.tz)
    idx = hist.index.get_indexer([target], method="nearest")[0]
    return float(hist["Close"].iloc[idx])


def _compute_return(ticker: str, start_date: str, end_date: str) -> Optional[float]:
    """Compute total return for ticker between two dates."""
    p1 = _get_price_at(ticker, start_date)
    p2 = _get_price_at(ticker, end_date)
    if p1 and p2 and p1 > 0:
        return (p2 - p1) / p1
    return None


def _max_drawdown_period(ticker: str, start_date: str, end_date: str) -> Optional[float]:
    """Compute max drawdown during period."""
    hist = _get_hist(ticker, start_date, end_date)
    if hist is None or len(hist) < 2:
        return None
    prices = hist["Close"]
    cummax = prices.cummax()
    dd = (prices - cummax) / cummax
    return float(dd.min())


def run_backtest(months_back: int = 6, top_n: int = 20) -> dict:
    """Run a backtest: score stocks as of N months ago, measure performance since.

    Returns backtest results with returns, alpha, win rate, drawdown.
    """
    config = load_config()
    now = datetime.now()
    start_date = (now - timedelta(days=months_back * 30)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")

    # Evaluation periods (from start_date forward)
    eval_periods = {}
    for m in [1, 3, 6, 12]:
        if m <= months_back:
            eval_end = (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=m * 30)).strftime("%Y-%m-%d")
            if eval_end <= end_date:
                eval_periods["%dm" % m] = eval_end

    if not eval_periods:
        eval_periods["full"] = end_date

    # Get tickers and fetch historical data for scoring
    tickers = get_sp500_tickers(cache_hours=168)  # use cached
    logger.info("Backtest: fetching data for %d tickers from %s", len(tickers), start_date)

    # Fetch data as of start_date (1y before start_date for technicals)
    data_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")

    stock_data: Dict[str, dict] = {}
    spy_hist = None

    for ticker in tickers[:100]:  # limit for speed
        try:
            t = yf.Ticker(ticker)
            hist = t.history(start=data_start, end=start_date)
            if hist is None or hist.empty:
                continue
            info = t.info or {}
            if not info.get("regularMarketPrice") and not info.get("currentPrice"):
                continue
            stock_data[ticker] = {
                "info": {k: v for k, v in info.items() if not callable(v)},
                "history": hist.to_dict(orient="list"),
                "history_index": [str(d) for d in hist.index],
            }
        except Exception:
            continue

    # Get SPY hist for beta
    try:
        spy_t = yf.Ticker("SPY")
        spy_full = spy_t.history(start=data_start, end=start_date)
        if spy_full is not None and not spy_full.empty:
            spy_hist = spy_full
    except Exception:
        pass

    # Score stocks
    results = []
    for ticker, data in stock_data.items():
        try:
            result = analyze_single(ticker, data, spy_hist)
            results.append(result)
        except Exception:
            continue

    if not results:
        return {"error": "No stocks could be analyzed", "months_back": months_back}

    weights = config.get("weights", {})
    ranked_df = compute_composite(results, weights)
    top_tickers = ranked_df.head(top_n)["ticker"].tolist()

    logger.info("Backtest: top %d picks from %s: %s", top_n, start_date, top_tickers[:5])

    # Measure performance
    period_results = {}
    for period_name, period_end in eval_periods.items():
        spy_return = _compute_return("SPY", start_date, period_end)

        stock_returns = []
        for ticker in top_tickers:
            ret = _compute_return(ticker, start_date, period_end)
            if ret is not None:
                stock_returns.append({"ticker": ticker, "return": round(ret, 4)})

        if not stock_returns:
            continue

        returns_arr = [s["return"] for s in stock_returns]
        avg_return = float(np.mean(returns_arr))
        alpha = avg_return - (spy_return or 0) if spy_return is not None else None
        win_rate = sum(1 for r in returns_arr if r > (spy_return or 0)) / len(returns_arr) if spy_return is not None else None

        # Max drawdown of equal-weighted portfolio (simplified)
        drawdowns = []
        for ticker in top_tickers[:10]:
            dd = _max_drawdown_period(ticker, start_date, period_end)
            if dd is not None:
                drawdowns.append(dd)
        avg_drawdown = float(np.mean(drawdowns)) if drawdowns else None

        period_results[period_name] = {
            "spy_return": round(spy_return, 4) if spy_return is not None else None,
            "portfolio_return": round(avg_return, 4),
            "alpha": round(alpha, 4) if alpha is not None else None,
            "win_rate": round(win_rate, 4) if win_rate is not None else None,
            "max_drawdown": round(avg_drawdown, 4) if avg_drawdown is not None else None,
            "stocks_measured": len(stock_returns),
            "stock_returns": stock_returns,
        }

    backtest_result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "months_back": months_back,
        "start_date": start_date,
        "end_date": end_date,
        "top_picks": top_tickers,
        "periods": period_results,
    }

    # Save to history
    _save_backtest(backtest_result)

    return backtest_result


def _save_backtest(result: dict):
    """Append backtest result to history file."""
    DATA_DIR.mkdir(exist_ok=True)
    history = load_backtest_history()
    history.append(result)
    # Keep last 50
    history = history[-50:]
    BACKTEST_FILE.write_text(json.dumps(history, indent=2, default=str))


def load_backtest_history() -> List[dict]:
    """Load all past backtest results."""
    if BACKTEST_FILE.exists():
        try:
            return json.loads(BACKTEST_FILE.read_text())
        except Exception:
            return []
    return []


# ---------------------------------------------------------------------------
# Rolling Backtest Engine
# ---------------------------------------------------------------------------

def _prefetch_all_history(tickers: List[str], years: int = 6) -> Dict[str, pd.DataFrame]:
    """Pre-fetch daily price history for all tickers in bulk.

    Fetches extra year for technical analysis lookback.
    """
    end = datetime.now()
    start = end - timedelta(days=years * 365 + 30)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    logger.info("Pre-fetching %d tickers from %s to %s", len(tickers), start_str, end_str)
    all_hist: Dict[str, pd.DataFrame] = {}

    # Batch download via yfinance
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            data = yf.download(batch, start=start_str, end=end_str, group_by="ticker", progress=False, threads=True)
            if data is None or data.empty:
                continue
            for t in batch:
                try:
                    if len(batch) == 1:
                        df = data
                    else:
                        df = data[t] if t in data.columns.get_level_values(0) else None
                    if df is not None and not df.empty and len(df) > 60:
                        # Drop rows with all NaN
                        df = df.dropna(how="all")
                        if len(df) > 60:
                            all_hist[t] = df
                except Exception:
                    continue
        except Exception:
            logger.warning("Batch download failed for batch starting at %d", i)
            continue
        logger.info("Pre-fetch progress: %d/%d tickers", min(i + batch_size, len(tickers)), len(tickers))

    logger.info("Pre-fetched history for %d tickers", len(all_hist))
    return all_hist


def _get_price_from_cache(hist: pd.DataFrame, date_str: str, days_tolerance: int = 5) -> Optional[float]:
    """Get closing price from pre-fetched history near a date."""
    if hist is None or hist.empty:
        return None
    target = pd.Timestamp(date_str)
    if hist.index.tz is not None:
        target = target.tz_localize(hist.index.tz)

    # Find nearest date within tolerance
    mask = (hist.index >= target - pd.Timedelta(days=days_tolerance)) & \
           (hist.index <= target + pd.Timedelta(days=days_tolerance))
    nearby = hist.loc[mask]
    if nearby.empty:
        return None

    idx = nearby.index.get_indexer([target], method="nearest")[0]
    close_col = "Close"
    if close_col not in nearby.columns:
        # Handle MultiIndex columns
        for col in nearby.columns:
            if "close" in str(col).lower():
                close_col = col
                break
    try:
        val = float(nearby[close_col].iloc[idx])
        return val if not np.isnan(val) else None
    except Exception:
        return None


def _compute_return_cached(hist: pd.DataFrame, start_date: str, end_date: str) -> Optional[float]:
    """Compute return using pre-fetched data."""
    p1 = _get_price_from_cache(hist, start_date)
    p2 = _get_price_from_cache(hist, end_date)
    if p1 and p2 and p1 > 0:
        return (p2 - p1) / p1
    return None


def _build_stock_data_at(ticker: str, hist_full: pd.DataFrame, as_of: str) -> Optional[dict]:
    """Build stock_data dict from pre-fetched history, sliced up to as_of date.

    Returns data in the format expected by analyze_single.
    """
    as_of_ts = pd.Timestamp(as_of)
    if hist_full.index.tz is not None:
        as_of_ts = as_of_ts.tz_localize(hist_full.index.tz)

    # Take 1 year of data ending at as_of for technical analysis
    start_ts = as_of_ts - pd.Timedelta(days=365)
    hist = hist_full.loc[(hist_full.index >= start_ts) & (hist_full.index <= as_of_ts)].copy()

    if hist.empty or len(hist) < 30:
        return None

    # Flatten MultiIndex columns if present (from yf.download with group_by='ticker')
    if isinstance(hist.columns, pd.MultiIndex):
        # Take second level (Price names: Open, High, Low, Close, Volume)
        hist.columns = hist.columns.get_level_values(-1)

    # Build a minimal info dict from price data
    close_col = "Close"
    vol_col = "Volume"
    for col in hist.columns:
        if "close" in str(col).lower():
            close_col = col
        if "volume" in str(col).lower():
            vol_col = col

    last_price = float(hist[close_col].iloc[-1])
    avg_volume = float(hist[vol_col].mean()) if vol_col in hist.columns else 0

    # Rename columns to simple names if needed
    rename_map = {}
    for col in hist.columns:
        lower = str(col).lower()
        if "open" in lower:
            rename_map[col] = "Open"
        elif "high" in lower:
            rename_map[col] = "High"
        elif "low" in lower:
            rename_map[col] = "Low"
        elif "close" in lower:
            rename_map[col] = "Close"
        elif "volume" in lower:
            rename_map[col] = "Volume"
    if rename_map:
        hist = hist.rename(columns=rename_map)

    info = {
        "regularMarketPrice": last_price,
        "currentPrice": last_price,
        "marketCap": last_price * avg_volume * 20,  # rough estimate
        "averageVolume": avg_volume,
        "sector": "Unknown",
        "industry": "Unknown",
        "shortName": ticker,
    }

    return {
        "info": info,
        "history": hist.to_dict(orient="list"),
        "history_index": [str(d) for d in hist.index],
    }


def get_rolling_backtest_status() -> dict:
    """Return current rolling backtest status."""
    return dict(_rolling_status)


def load_rolling_backtest_cache() -> Optional[dict]:
    """Load cached rolling backtest results if fresh (< 24h)."""
    if ROLLING_BACKTEST_FILE.exists():
        try:
            age_h = (time.time() - ROLLING_BACKTEST_FILE.stat().st_mtime) / 3600
            if age_h < 24:
                return json.loads(ROLLING_BACKTEST_FILE.read_text())
        except Exception:
            pass
    return None


def run_rolling_backtest(years: int = 5, top_n: int = 20, max_stocks: int = 100) -> dict:
    """Run rolling monthly backtest over past N years.

    For each month:
    - Score stocks using data available at that time
    - Pick top N
    - Measure 1m/3m/6m forward returns
    - Compare vs SPY

    Returns aggregate stats for conservative/balanced/aggressive strategies.
    """
    global _rolling_status

    # Check cache first
    cached = load_rolling_backtest_cache()
    if cached and cached.get("years") == years:
        logger.info("Returning cached rolling backtest results")
        return cached

    if _rolling_status["running"]:
        return {"error": "Rolling backtest already in progress", "status": dict(_rolling_status)}

    _rolling_status = {"running": True, "progress": 0, "total": 0, "message": "Starting..."}

    try:
        return _run_rolling_backtest_impl(years, top_n, max_stocks)
    finally:
        _rolling_status["running"] = False


def _run_rolling_backtest_impl(years: int, top_n: int, max_stocks: int) -> dict:
    """Implementation of rolling backtest."""
    global _rolling_status

    now = datetime.now()
    strategies = ["conservative", "balanced", "aggressive"]
    periods_count = years * 12

    # Generate evaluation dates (first of each month going back)
    eval_dates: List[str] = []
    for m in range(periods_count):
        dt = now - timedelta(days=(m + 1) * 30)
        # Snap to first of month
        dt = dt.replace(day=1)
        eval_dates.append(dt.strftime("%Y-%m-%d"))
    eval_dates.reverse()  # chronological order

    _rolling_status["total"] = len(eval_dates)
    _rolling_status["message"] = "Pre-fetching price history..."
    logger.info("Rolling backtest: %d periods, pre-fetching data...", len(eval_dates))

    # Get tickers
    tickers = get_sp500_tickers(cache_hours=168)
    # Limit for speed
    tickers_to_use = tickers[:max_stocks]
    # Always include SPY
    if "SPY" not in tickers_to_use:
        tickers_to_use.append("SPY")

    # Pre-fetch ALL history once
    all_hist = _prefetch_all_history(tickers_to_use, years=years + 2)

    if "SPY" not in all_hist:
        # Try fetching SPY separately
        try:
            spy_data = yf.download("SPY", period="%dy" % (years + 2), progress=False)
            if spy_data is not None and not spy_data.empty:
                all_hist["SPY"] = spy_data
        except Exception:
            pass

    if "SPY" not in all_hist:
        _rolling_status["message"] = "Failed to fetch SPY data"
        return {"error": "Could not fetch SPY data"}

    spy_hist = all_hist["SPY"]
    available_tickers = [t for t in tickers_to_use if t in all_hist and t != "SPY"]

    _rolling_status["message"] = "Running %d periods across %d tickers..." % (len(eval_dates), len(available_tickers))
    logger.info("Available tickers for backtest: %d", len(available_tickers))

    # Build SPY hist for beta calculation (simple version)
    spy_hist_for_beta = spy_hist.copy()
    # Flatten MultiIndex columns if present
    if isinstance(spy_hist_for_beta.columns, pd.MultiIndex):
        spy_hist_for_beta.columns = spy_hist_for_beta.columns.get_level_values(-1)
    # Normalize column names
    rename_map = {}
    for col in spy_hist_for_beta.columns:
        lower = str(col).lower()
        if "close" in lower:
            rename_map[col] = "Close"
        elif "open" in lower:
            rename_map[col] = "Open"
        elif "high" in lower:
            rename_map[col] = "High"
        elif "low" in lower:
            rename_map[col] = "Low"
        elif "volume" in lower:
            rename_map[col] = "Volume"
    if rename_map:
        spy_hist_for_beta = spy_hist_for_beta.rename(columns=rename_map)

    # Results per strategy
    strategy_results: Dict[str, Dict] = {s: {"periods": []} for s in strategies}

    for period_idx, eval_date in enumerate(eval_dates):
        _rolling_status["progress"] = period_idx + 1
        _rolling_status["message"] = "Period %d/%d: %s" % (period_idx + 1, len(eval_dates), eval_date)
        logger.info("Rolling backtest period %d/%d: %s", period_idx + 1, len(eval_dates), eval_date)

        # Build stock data as of eval_date
        stock_analyses: List[dict] = []
        for ticker in available_tickers:
            try:
                stock_data = _build_stock_data_at(ticker, all_hist[ticker], eval_date)
                if stock_data is None:
                    if period_idx == 0:
                        logger.debug("_build_stock_data_at returned None for %s at %s", ticker, eval_date)
                    continue
                # Slice SPY hist for beta
                as_of_ts = pd.Timestamp(eval_date)
                if spy_hist_for_beta.index.tz is not None:
                    as_of_ts = as_of_ts.tz_localize(spy_hist_for_beta.index.tz)
                spy_slice = spy_hist_for_beta.loc[spy_hist_for_beta.index <= as_of_ts].tail(252)

                result = analyze_single(ticker, stock_data, spy_slice if len(spy_slice) > 30 else None)
                stock_analyses.append(result)
            except Exception as e:
                if period_idx == 0:
                    logger.warning("Failed to analyze %s for %s: %s", ticker, eval_date, str(e))
                continue

        if len(stock_analyses) < 10:
            logger.warning("Only %d stocks analyzed for %s, skipping (available: %d)", len(stock_analyses), eval_date, len(available_tickers))
            continue

        # Score with each strategy and measure forward returns
        for strategy in strategies:
            try:
                config = load_config()
                weights = config.get("weights", {})
                ranked_df = compute_composite(stock_analyses, weights, strategy=strategy)
                top_tickers = ranked_df.head(top_n)["ticker"].tolist()

                # Measure forward returns at 1m, 3m, 6m
                forward_returns: Dict[str, Optional[float]] = {}
                spy_forward: Dict[str, Optional[float]] = {}

                for horizon_name, horizon_days in [("1m", 30), ("3m", 90), ("6m", 180)]:
                    end_dt = datetime.strptime(eval_date, "%Y-%m-%d") + timedelta(days=horizon_days)
                    end_str = end_dt.strftime("%Y-%m-%d")

                    # Don't measure if end date is in the future
                    if end_dt > now:
                        forward_returns[horizon_name] = None
                        spy_forward[horizon_name] = None
                        continue

                    # SPY return
                    spy_ret = _compute_return_cached(spy_hist, eval_date, end_str)
                    spy_forward[horizon_name] = spy_ret

                    # Portfolio return (equal-weighted)
                    rets = []
                    for t in top_tickers:
                        if t in all_hist:
                            r = _compute_return_cached(all_hist[t], eval_date, end_str)
                            if r is not None:
                                rets.append(r)
                    forward_returns[horizon_name] = float(np.mean(rets)) if rets else None

                # Calculate alpha for each horizon
                period_data = {
                    "date": eval_date,
                    "top_picks": top_tickers[:5],  # save top 5 for reference
                    "num_scored": len(stock_analyses),
                }
                for h in ["1m", "3m", "6m"]:
                    pr = forward_returns.get(h)
                    sr = spy_forward.get(h)
                    period_data["%s_return" % h] = round(pr, 4) if pr is not None else None
                    period_data["%s_spy" % h] = round(sr, 4) if sr is not None else None
                    if pr is not None and sr is not None:
                        period_data["%s_alpha" % h] = round(pr - sr, 4)
                    else:
                        period_data["%s_alpha" % h] = None

                strategy_results[strategy]["periods"].append(period_data)
            except Exception:
                logger.warning("Failed strategy %s for period %s", strategy, eval_date, exc_info=True)
                continue

    # Compute aggregate stats for each strategy and horizon
    _rolling_status["message"] = "Computing aggregate statistics..."

    final_results: Dict[str, dict] = {}
    for strategy in strategies:
        periods = strategy_results[strategy]["periods"]
        strat_result: Dict[str, object] = {"periods": periods, "horizons": {}}

        for h in ["1m", "3m", "6m"]:
            alphas = [p["%s_alpha" % h] for p in periods if p.get("%s_alpha" % h) is not None]
            returns = [p["%s_return" % h] for p in periods if p.get("%s_return" % h) is not None]
            spy_returns = [p["%s_spy" % h] for p in periods if p.get("%s_spy" % h) is not None]

            if not alphas:
                strat_result["horizons"][h] = {"insufficient_data": True}
                continue

            alphas_arr = np.array(alphas)
            win_rate = float(np.sum(alphas_arr > 0) / len(alphas_arr))
            avg_alpha = float(np.mean(alphas_arr))
            std_alpha = float(np.std(alphas_arr, ddof=1)) if len(alphas_arr) > 1 else 0.0

            # Sharpe ratio of alpha stream
            sharpe = float(avg_alpha / std_alpha * np.sqrt(12)) if std_alpha > 0 else 0.0

            # t-test: is alpha significantly different from 0?
            if len(alphas_arr) > 2:
                t_stat_val, p_value_val = stats.ttest_1samp(alphas_arr, 0)
                t_stat_val = float(t_stat_val)
                p_value_val = float(p_value_val)
            else:
                t_stat_val = 0.0
                p_value_val = 1.0

            # Best/worst period
            best_idx = int(np.argmax(alphas_arr))
            worst_idx = int(np.argmin(alphas_arr))
            valid_periods = [p for p in periods if p.get("%s_alpha" % h) is not None]

            strat_result["horizons"][h] = {
                "num_periods": len(alphas),
                "win_rate": round(win_rate, 4),
                "avg_alpha": round(avg_alpha, 4),
                "avg_return": round(float(np.mean(returns)), 4) if returns else None,
                "avg_spy_return": round(float(np.mean(spy_returns)), 4) if spy_returns else None,
                "std_alpha": round(std_alpha, 4),
                "sharpe_ratio": round(sharpe, 4),
                "t_stat": round(t_stat_val, 4),
                "p_value": round(p_value_val, 4),
                "best_period": {
                    "date": valid_periods[best_idx]["date"] if best_idx < len(valid_periods) else None,
                    "alpha": round(float(alphas_arr[best_idx]), 4),
                },
                "worst_period": {
                    "date": valid_periods[worst_idx]["date"] if worst_idx < len(valid_periods) else None,
                    "alpha": round(float(alphas_arr[worst_idx]), 4),
                },
                "consistency": round(win_rate, 4),  # same as win rate
                "significant": p_value_val < 0.05,
            }

        final_results[strategy] = strat_result

    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "years": years,
        "periods_evaluated": len(eval_dates),
        "tickers_used": len(available_tickers),
        "top_n": top_n,
        "strategies": final_results,
    }

    # Cache results (only if we have actual data)
    total_periods = sum(len(v.get("periods", [])) for v in final_results.values())
    DATA_DIR.mkdir(exist_ok=True)
    if total_periods > 0:
        ROLLING_BACKTEST_FILE.write_text(json.dumps(result, indent=2, default=str))
    _rolling_status["message"] = "Complete"
    logger.info("Rolling backtest complete, saved to %s", ROLLING_BACKTEST_FILE)

    return result
