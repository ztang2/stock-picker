"""ML-based stock scoring model using XGBoost.

Trains on historical snapshot data (or synthetic reconstructions) to predict
forward 1-month returns. Provides both classification (beat SPY?) and regression
(predicted return) models.
"""

import json
import logging
import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ML_DIR = DATA_DIR / "ml"
SNAPSHOT_DIR = DATA_DIR / "daily_snapshots"
MODEL_PATH = ML_DIR / "model.pkl"
METRICS_PATH = ML_DIR / "metrics.json"
COMPARISON_PATH = ML_DIR / "model_comparison.json"
ENSEMBLE_PATH = ML_DIR / "ensemble_results.json"
SPECIALIZED_ENSEMBLE_PATH = ML_DIR / "specialized_ensemble_results.json"

BASE_FEATURE_COLS = [
    "fundamentals_pct", "valuation_pct", "technicals_pct", "risk_pct",
    "growth_pct", "sentiment_pct", "sector_composite",
    "entry_score", "composite_score",
    "rsi", "macd_histogram", "ma50_ratio", "ma200_ratio", "volume_trend",
    "market_regime_bull", "market_regime_bear",
]

# Interaction / engineered features added during training
ENGINEERED_COLS = [
    "rsi_x_regime_bull", "momentum_proxy", "value_momentum",
    "tech_x_growth", "rsi_oversold", "rsi_overbought",
    "above_ma200", "score_rank",
]

# For backward compat
FEATURE_COLS = BASE_FEATURE_COLS


def _ensure_dirs():
    ML_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _load_snapshots() -> List[dict]:
    """Load all daily snapshot JSON files."""
    snapshots = []
    if not SNAPSHOT_DIR.exists():
        return snapshots
    for f in sorted(SNAPSHOT_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if "date" not in data:
                data["date"] = f.stem  # filename is YYYY-MM-DD
            snapshots.append(data)
        except Exception:
            logger.warning(f"Failed to load snapshot {f}")
    return snapshots


def _get_price_data(tickers: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    """Fetch historical price data via yfinance."""
    import yfinance as yf
    result = {}
    # Batch download
    try:
        data = yf.download(tickers, start=start, end=end, progress=False, group_by="ticker", threads=True)
        if len(tickers) == 1:
            if not data.empty:
                result[tickers[0]] = data
        else:
            for t in tickers:
                try:
                    df = data[t].dropna(how="all")
                    if not df.empty:
                        result[t] = df
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Batch download failed: {e}")
    return result


def _compute_forward_return(prices: pd.DataFrame, date: str, days: int = 21) -> Optional[float]:
    """Compute forward return from date over next `days` trading days."""
    try:
        dt = pd.Timestamp(date)
        mask = prices.index >= dt
        future = prices.loc[mask]
        if len(future) < days + 1:
            return None
        start_price = future.iloc[0]["Close"]
        end_price = future.iloc[min(days, len(future) - 1)]["Close"]
        if start_price <= 0:
            return None
        return float((end_price - start_price) / start_price)
    except Exception:
        return None


def _compute_spy_return(spy_prices: pd.DataFrame, date: str, days: int = 21) -> Optional[float]:
    return _compute_forward_return(spy_prices, date, days)


def _extract_features_from_stock(stock: dict, regime: str = "sideways") -> dict:
    """Extract feature dict from a single stock entry in scan results.
    
    Fields come from pipeline.py's ranked output. Computes derived features
    (ma50_ratio, ma200_ratio) from raw values when not directly available.
    """
    # Compute MA ratios from price and MA values
    price = stock.get("current_price")
    ma50 = stock.get("ma50")
    ma200 = stock.get("ma200")
    ma50_ratio = (price / ma50) if (price and ma50 and ma50 > 0) else None
    ma200_ratio = (price / ma200) if (price and ma200 and ma200 > 0) else None
    
    feats = {
        "fundamentals_pct": stock.get("fundamentals_pct"),
        "valuation_pct": stock.get("valuation_pct"),
        "technicals_pct": stock.get("technicals_pct"),
        "risk_pct": stock.get("risk_pct"),
        "growth_pct": stock.get("growth_pct"),
        "sentiment_pct": stock.get("sentiment_pct"),
        "sector_composite": stock.get("sector_composite"),
        "entry_score": stock.get("entry_score"),
        "composite_score": stock.get("composite_score"),
        "rsi": stock.get("rsi"),
        "macd_histogram": stock.get("macd_histogram"),
        "ma50_ratio": ma50_ratio,
        "ma200_ratio": ma200_ratio,
        "volume_trend": stock.get("volume_trend"),
        "adx": stock.get("adx"),
        "volatility": stock.get("volatility"),
        "beta": stock.get("beta"),
        "smart_money_score": stock.get("smart_money_score"),
        "market_regime_bull": 1.0 if regime == "bull" else 0.0,
        "market_regime_bear": 1.0 if regime == "bear" else 0.0,
    }
    return feats


def _generate_synthetic_data(months: int = 18) -> pd.DataFrame:
    """Generate training data by reconstructing scores from historical prices.
    
    Uses existing scorer infrastructure on historical data to create features,
    then computes actual forward returns as labels.
    """
    import yfinance as yf
    from .technicals import score_technicals, _rsi, _macd_signal

    logger.info(f"Generating synthetic training data for {months} months...")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30 + 60)  # extra buffer

    # Get S&P 500 tickers (use cached list)
    sp500_file = DATA_DIR / "sp500_tickers.json"
    if sp500_file.exists():
        tickers = json.loads(sp500_file.read_text())[:100]  # top 100 for speed
    else:
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "JNJ",
                    "WMT", "PG", "UNH", "HD", "MA", "DIS", "PYPL", "BAC", "ADBE", "CRM",
                    "NFLX", "COST", "PEP", "TMO", "ABT", "AVGO", "ACN", "MRK", "LLY", "DHR"]

    # Download all price data
    logger.info(f"Downloading price data for {len(tickers)} tickers...")
    price_data = _get_price_data(
        tickers + ["SPY"],
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )

    spy_prices = price_data.pop("SPY", None)
    if spy_prices is None or spy_prices.empty:
        logger.error("Failed to get SPY data")
        return pd.DataFrame()

    # Detect market regime at each sample date using SPY
    from .market_regime import detect_market_regime

    rows = []
    # Sample every 5 trading days (weekly) for more training data
    sample_dates = spy_prices.index[200::5]  # need 200 bars for MA200

    for sample_date in sample_dates:
        date_str = sample_date.strftime("%Y-%m-%d")

        # Forward SPY return
        spy_ret = _compute_spy_return(spy_prices, date_str)
        if spy_ret is None:
            continue

        # Market regime at this date
        spy_hist_slice = spy_prices.loc[:sample_date]
        regime_info = detect_market_regime(spy_hist_slice)
        regime = regime_info.get("regime", "sideways")

        for ticker in tickers:
            if ticker not in price_data:
                continue
            hist = price_data[ticker]
            hist_slice = hist.loc[:sample_date]

            if len(hist_slice) < 200:
                continue

            close = hist_slice["Close"]
            current_price = float(close.iloc[-1])

            # Compute technicals
            rsi_val = _rsi(close)
            macd_val = _macd_signal(close)
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])
            vol_20 = float(hist_slice["Volume"].tail(20).mean())
            vol_50 = float(hist_slice["Volume"].tail(50).mean())

            # Forward return for this stock
            stock_ret = _compute_forward_return(hist, date_str)
            if stock_ret is None:
                continue

            # Compute synthetic scores based on technicals (simplified)
            tech_data = score_technicals(hist_slice)

            # Compute real features from price history (no data leakage)
            # These are computed AT sample_date, predicting FUTURE returns
            volatility = float(close.pct_change().tail(60).std() * np.sqrt(252) * 100)
            
            # Use REAL scoring functions where possible
            from .risk import score_risk
            risk_data = score_risk(hist_slice, spy_prices.loc[:sample_date] if spy_prices is not None else None)
            
            # ADX for trend strength
            adx_val = None
            if len(hist_slice) >= 20:
                try:
                    high = hist_slice["High"]
                    low = hist_slice["Low"]
                    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
                    atr14 = tr.rolling(14).mean()
                    plus_dm = (high.diff()).clip(lower=0)
                    minus_dm = (-low.diff()).clip(lower=0)
                    plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
                    minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
                    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
                    adx_val = float(dx.rolling(14).mean().iloc[-1])
                    if pd.isna(adx_val):
                        adx_val = None
                except Exception:
                    pass

            row = {
                "date": date_str,
                "ticker": ticker,
                # Percentile scores set to None — model learns from technicals + regime
                # (fundamentals/valuation/growth not available historically without financial data)
                "fundamentals_pct": None,
                "valuation_pct": None,
                "technicals_pct": tech_data.get("score") or 50,
                "risk_pct": risk_data.get("score") if risk_data else None,
                "growth_pct": None,
                "sentiment_pct": None,
                "sector_composite": None,
                "entry_score": None,
                "composite_score": tech_data.get("score") or 50,
                "rsi": rsi_val,
                "macd_histogram": macd_val,
                "ma50_ratio": current_price / ma50 if ma50 > 0 else None,
                "ma200_ratio": current_price / ma200 if ma200 > 0 else None,
                "volume_trend": vol_20 / vol_50 if vol_50 > 0 else None,
                "adx": adx_val,
                "volatility": volatility,
                "beta": risk_data.get("beta") if risk_data else None,
                "smart_money_score": None,  # Not available historically
                "market_regime_bull": 1.0 if regime == "bull" else 0.0,
                "market_regime_bear": 1.0 if regime == "bear" else 0.0,
                "forward_return": stock_ret,
                "spy_return": spy_ret,
                "excess_return": stock_ret - spy_ret,
                "beat_spy": 1 if stock_ret > spy_ret else 0,
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    logger.info(f"Generated {len(df)} synthetic training samples across {len(sample_dates)} dates")
    return df


def _build_dataset() -> pd.DataFrame:
    """Build training dataset from snapshots or synthetic data."""
    snapshots = _load_snapshots()

    if len(snapshots) >= 30:
        # Use real snapshot data
        logger.info(f"Building dataset from {len(snapshots)} snapshots")
        import yfinance as yf

        all_tickers = set()
        for snap in snapshots:
            for stock in snap.get("top", snap.get("stocks", [])):
                all_tickers.add(stock["ticker"])

        dates = [s["date"] for s in snapshots]
        min_date = min(dates)
        max_date_dt = datetime.strptime(max(dates), "%Y-%m-%d") + timedelta(days=35)

        price_data = _get_price_data(
            list(all_tickers) + ["SPY"],
            min_date,
            max_date_dt.strftime("%Y-%m-%d"),
        )
        spy_prices = price_data.pop("SPY", None)

        rows = []
        for snap in snapshots:
            date_str = snap["date"]
            regime_info = snap.get("market_regime", {})
            regime = regime_info.get("regime", "sideways") if isinstance(regime_info, dict) else "sideways"
            spy_ret = _compute_spy_return(spy_prices, date_str) if spy_prices is not None else None

            for stock in snap.get("top", snap.get("stocks", [])):
                ticker = stock["ticker"]
                if ticker not in price_data or spy_ret is None:
                    continue
                stock_ret = _compute_forward_return(price_data[ticker], date_str)
                if stock_ret is None:
                    continue

                feats = _extract_features_from_stock(stock, regime)
                feats["date"] = date_str
                feats["ticker"] = ticker
                feats["forward_return"] = stock_ret
                feats["spy_return"] = spy_ret
                feats["excess_return"] = stock_ret - spy_ret
                feats["beat_spy"] = 1 if stock_ret > spy_ret else 0
                rows.append(feats)

        df = pd.DataFrame(rows)
        if len(df) >= 50:
            logger.info(f"Built dataset with {len(df)} real samples")
            return df

    # Fall back to synthetic data
    logger.info("Insufficient snapshot data, generating synthetic training data...")
    return _generate_synthetic_data()


def _walk_forward_evaluate(df, X, y_cls, y_reg, all_features, months_history, build_clf_fn, build_reg_fn):
    """Run walk-forward validation for a given model builder pair.
    
    Returns (wf_preds_cls, wf_actuals_cls, wf_preds_reg, wf_actuals_reg).
    """
    dates = sorted(df["date"].unique())
    n_dates = len(dates)
    train_months = min(months_history, n_dates - 2)

    wf_preds_cls, wf_actuals_cls = [], []
    wf_preds_reg, wf_actuals_reg = [], []

    for i in range(train_months, n_dates):
        train_dates = dates[max(0, i - train_months):i]
        test_date = dates[i]

        train_mask = df["date"].isin(train_dates)
        test_mask = df["date"] == test_date

        X_train, y_train_cls, y_train_reg = X[train_mask], y_cls[train_mask], y_reg[train_mask]
        X_test, y_test_cls, y_test_reg = X[test_mask], y_cls[test_mask], y_reg[test_mask]

        if len(X_train) < 10 or len(X_test) == 0:
            continue

        clf = build_clf_fn()
        clf.fit(X_train, y_train_cls)
        wf_preds_cls.extend(clf.predict(X_test))
        wf_actuals_cls.extend(y_test_cls)

        reg = build_reg_fn()
        reg.fit(X_train, y_train_reg)
        wf_preds_reg.extend(reg.predict(X_test))
        wf_actuals_reg.extend(y_test_reg)

    return wf_preds_cls, wf_actuals_cls, wf_preds_reg, wf_actuals_reg


def _compute_metrics(wf_preds_cls, wf_actuals_cls, wf_preds_reg, wf_actuals_reg, total_samples):
    """Compute standard metrics dict from walk-forward results."""
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    metrics = {"total_samples": total_samples, "walk_forward_samples": len(wf_preds_cls)}
    if wf_preds_cls:
        metrics["accuracy"] = round(accuracy_score(wf_actuals_cls, wf_preds_cls), 4)
        metrics["precision"] = round(precision_score(wf_actuals_cls, wf_preds_cls, zero_division=0), 4)
        metrics["recall"] = round(recall_score(wf_actuals_cls, wf_preds_cls, zero_division=0), 4)
        metrics["f1"] = round(f1_score(wf_actuals_cls, wf_preds_cls, zero_division=0), 4)
    if wf_preds_reg:
        actuals = np.array(wf_actuals_reg)
        preds = np.array(wf_preds_reg)
        metrics["regression_mae"] = round(float(np.mean(np.abs(actuals - preds))), 4)
        corr = float(np.corrcoef(actuals, preds)[0, 1]) if len(actuals) > 1 else 0
        metrics["regression_corr"] = round(corr if not np.isnan(corr) else 0, 4)
    return metrics


def _walk_forward_ensemble(df, X, y_cls, y_reg, all_features, months_history,
                           xgb_clf_builder, xgb_reg_builder, lgb_clf_builder, lgb_reg_builder):
    """Walk-forward validation that collects per-fold predictions for all 5 approaches.

    Returns a dict keyed by approach name, each value is (preds_cls, actuals_cls, preds_reg, actuals_reg).
    Also returns optimized ensemble weight and fitted meta-learner for final training.
    """
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.metrics import accuracy_score

    dates = sorted(df["date"].unique())
    n_dates = len(dates)
    train_months = min(months_history, n_dates - 2)

    # Collectors for each approach
    results = {name: {"cls": [], "cls_act": [], "reg": [], "reg_act": []}
               for name in ["xgboost", "lightgbm", "simple_avg", "weighted_avg", "meta_learner"]}

    # Track per-fold individual model accuracy to optimize weights
    fold_xgb_acc = []
    fold_lgb_acc = []

    # Collect meta-learner training data across folds
    meta_X_cls_all, meta_y_cls_all = [], []
    meta_X_reg_all, meta_y_reg_all = [], []

    for i in range(train_months, n_dates):
        train_dates = dates[max(0, i - train_months):i]
        test_date = dates[i]

        train_mask = df["date"].isin(train_dates)
        test_mask = df["date"] == test_date

        X_train, y_train_cls, y_train_reg = X[train_mask], y_cls[train_mask], y_reg[train_mask]
        X_test, y_test_cls, y_test_reg = X[test_mask], y_cls[test_mask], y_reg[test_mask]

        if len(X_train) < 10 or len(X_test) == 0:
            continue

        # Train both models
        xgb_clf = xgb_clf_builder(); xgb_clf.fit(X_train, y_train_cls)
        lgb_clf = lgb_clf_builder(); lgb_clf.fit(X_train, y_train_cls)
        xgb_reg = xgb_reg_builder(); xgb_reg.fit(X_train, y_train_reg)
        lgb_reg = lgb_reg_builder(); lgb_reg.fit(X_train, y_train_reg)

        # Individual predictions
        xgb_cls_pred = xgb_clf.predict(X_test)
        lgb_cls_pred = lgb_clf.predict(X_test)
        xgb_cls_prob = xgb_clf.predict_proba(X_test)[:, 1]
        lgb_cls_prob = lgb_clf.predict_proba(X_test)[:, 1]
        xgb_reg_pred = xgb_reg.predict(X_test)
        lgb_reg_pred = lgb_reg.predict(X_test)

        # Store individual model results
        results["xgboost"]["cls"].extend(xgb_cls_pred)
        results["xgboost"]["cls_act"].extend(y_test_cls)
        results["xgboost"]["reg"].extend(xgb_reg_pred)
        results["xgboost"]["reg_act"].extend(y_test_reg)

        results["lightgbm"]["cls"].extend(lgb_cls_pred)
        results["lightgbm"]["cls_act"].extend(y_test_cls)
        results["lightgbm"]["reg"].extend(lgb_reg_pred)
        results["lightgbm"]["reg_act"].extend(y_test_reg)

        # Simple average (50/50)
        avg_prob = 0.5 * xgb_cls_prob + 0.5 * lgb_cls_prob
        avg_cls = (avg_prob >= 0.5).astype(int)
        avg_reg = 0.5 * xgb_reg_pred + 0.5 * lgb_reg_pred
        results["simple_avg"]["cls"].extend(avg_cls)
        results["simple_avg"]["cls_act"].extend(y_test_cls)
        results["simple_avg"]["reg"].extend(avg_reg)
        results["simple_avg"]["reg_act"].extend(y_test_reg)

        # Track per-fold accuracy for weight optimization
        if len(y_test_cls) > 0:
            fold_xgb_acc.append(accuracy_score(y_test_cls, xgb_cls_pred))
            fold_lgb_acc.append(accuracy_score(y_test_cls, lgb_cls_pred))

        # Weighted average: use cumulative accuracy up to this fold as weights
        if fold_xgb_acc:
            cum_xgb = np.mean(fold_xgb_acc)
            cum_lgb = np.mean(fold_lgb_acc)
            total = cum_xgb + cum_lgb
            w_xgb = cum_xgb / total if total > 0 else 0.5
        else:
            w_xgb = 0.5
        w_lgb = 1 - w_xgb
        wavg_prob = w_xgb * xgb_cls_prob + w_lgb * lgb_cls_prob
        wavg_cls = (wavg_prob >= 0.5).astype(int)
        wavg_reg = w_xgb * xgb_reg_pred + w_lgb * lgb_reg_pred
        results["weighted_avg"]["cls"].extend(wavg_cls)
        results["weighted_avg"]["cls_act"].extend(y_test_cls)
        results["weighted_avg"]["reg"].extend(wavg_reg)
        results["weighted_avg"]["reg_act"].extend(y_test_reg)

        # Meta-learner: train on accumulated folds, predict on current test
        meta_feats_test = np.column_stack([xgb_cls_prob, lgb_cls_prob])
        meta_feats_reg_test = np.column_stack([xgb_reg_pred, lgb_reg_pred])

        if len(meta_X_cls_all) >= 10:
            meta_clf = LogisticRegression(C=1.0, solver="lbfgs", max_iter=200)
            meta_clf.fit(np.array(meta_X_cls_all), np.array(meta_y_cls_all))
            meta_cls_pred = meta_clf.predict(meta_feats_test)

            meta_reg_m = Ridge(alpha=1.0)
            meta_reg_m.fit(np.array(meta_X_reg_all), np.array(meta_y_reg_all))
            meta_reg_pred = meta_reg_m.predict(meta_feats_reg_test)
        else:
            # Not enough data for meta-learner yet, fall back to simple avg
            meta_cls_pred = avg_cls
            meta_reg_pred = avg_reg

        results["meta_learner"]["cls"].extend(meta_cls_pred)
        results["meta_learner"]["cls_act"].extend(y_test_cls)
        results["meta_learner"]["reg"].extend(meta_reg_pred)
        results["meta_learner"]["reg_act"].extend(y_test_reg)

        # Accumulate meta-learner training data
        meta_X_cls_all.extend(meta_feats_test.tolist())
        meta_y_cls_all.extend(y_test_cls.tolist())
        meta_X_reg_all.extend(meta_feats_reg_test.tolist())
        meta_y_reg_all.extend(y_test_reg.tolist())

    # Compute optimized weight from full walk-forward
    if fold_xgb_acc:
        cum_xgb = np.mean(fold_xgb_acc)
        cum_lgb = np.mean(fold_lgb_acc)
        total = cum_xgb + cum_lgb
        opt_w_xgb = round(cum_xgb / total if total > 0 else 0.5, 4)
    else:
        opt_w_xgb = 0.5

    return results, opt_w_xgb


def _consensus_signal(xgb_prob: float, lgb_return: float) -> str:
    """Compute consensus signal from specialized models."""
    if xgb_prob < 0.45 or lgb_return < -0.02:
        return "AVOID"
    if xgb_prob > 0.65 and lgb_return > 0.02:
        return "STRONG_BUY"
    if xgb_prob > 0.55 and lgb_return > 0.0:
        return "BUY"
    return "HOLD"


def _walk_forward_specialized(df, X, y_cls, y_reg, all_features, months_history,
                               xgb_clf_builder, lgb_reg_builder):
    """Walk-forward for specialized ensemble: XGB classifier + LGB regressor.
    
    Returns metrics dict and detailed per-prediction results.
    """
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    dates = sorted(df["date"].unique())
    n_dates = len(dates)
    train_months = min(months_history, n_dates - 2)

    all_preds = []  # list of dicts with xgb_prob, lgb_return, actual_beat_spy, actual_excess

    for i in range(train_months, n_dates):
        train_dates = dates[max(0, i - train_months):i]
        test_date = dates[i]

        train_mask = df["date"].isin(train_dates)
        test_mask = df["date"] == test_date

        X_train, y_train_cls, y_train_reg = X[train_mask], y_cls[train_mask], y_reg[train_mask]
        X_test, y_test_cls, y_test_reg = X[test_mask], y_cls[test_mask], y_reg[test_mask]

        if len(X_train) < 10 or len(X_test) == 0:
            continue

        # XGBoost classifier only
        xgb_clf = xgb_clf_builder()
        xgb_clf.fit(X_train, y_train_cls)
        xgb_probs = xgb_clf.predict_proba(X_test)[:, 1]

        # LightGBM regressor only
        lgb_reg = lgb_reg_builder()
        lgb_reg.fit(X_train, y_train_reg)
        lgb_returns = lgb_reg.predict(X_test)

        for j in range(len(X_test)):
            all_preds.append({
                "xgb_prob": float(xgb_probs[j]),
                "lgb_return": float(lgb_returns[j]),
                "actual_beat_spy": int(y_test_cls.iloc[j] if hasattr(y_test_cls, 'iloc') else y_test_cls[j]),
                "actual_excess": float(y_test_reg.iloc[j] if hasattr(y_test_reg, 'iloc') else y_test_reg[j]),
                "signal": _consensus_signal(float(xgb_probs[j]), float(lgb_returns[j])),
            })

    if not all_preds:
        return {}, []

    # Consensus buys: both agree (XGB >55% AND LGB >0%)
    consensus_buys = [p for p in all_preds if p["xgb_prob"] > 0.55 and p["lgb_return"] > 0.0]
    strong_buys = [p for p in all_preds if p["signal"] == "STRONG_BUY"]
    avoids = [p for p in all_preds if p["signal"] == "AVOID"]

    # Classification metrics: treat consensus buy as predicted positive
    pred_cls = [1 if p["xgb_prob"] > 0.55 and p["lgb_return"] > 0.0 else 0 for p in all_preds]
    actual_cls = [p["actual_beat_spy"] for p in all_preds]

    metrics = {
        "total_samples": len(df),
        "walk_forward_samples": len(all_preds),
        "accuracy": round(accuracy_score(actual_cls, pred_cls), 4),
        "precision": round(precision_score(actual_cls, pred_cls, zero_division=0), 4),
        "recall": round(recall_score(actual_cls, pred_cls, zero_division=0), 4),
        "f1": round(f1_score(actual_cls, pred_cls, zero_division=0), 4),
    }

    # Regression: use LGB predictions directly
    lgb_preds = [p["lgb_return"] for p in all_preds]
    lgb_actuals = [p["actual_excess"] for p in all_preds]
    metrics["regression_mae"] = round(float(np.mean(np.abs(np.array(lgb_actuals) - np.array(lgb_preds)))), 4)
    corr = float(np.corrcoef(lgb_actuals, lgb_preds)[0, 1]) if len(lgb_actuals) > 1 else 0
    metrics["regression_corr"] = round(corr if not np.isnan(corr) else 0, 4)

    # Consensus buy accuracy
    if consensus_buys:
        buy_accuracy = sum(1 for p in consensus_buys if p["actual_beat_spy"] == 1) / len(consensus_buys)
        avg_excess_when_buy = np.mean([p["actual_excess"] for p in consensus_buys])
    else:
        buy_accuracy = 0
        avg_excess_when_buy = 0

    if strong_buys:
        strong_buy_accuracy = sum(1 for p in strong_buys if p["actual_beat_spy"] == 1) / len(strong_buys)
        avg_excess_strong = np.mean([p["actual_excess"] for p in strong_buys])
    else:
        strong_buy_accuracy = 0
        avg_excess_strong = 0

    if avoids:
        avoid_accuracy = sum(1 for p in avoids if p["actual_beat_spy"] == 0) / len(avoids)
    else:
        avoid_accuracy = 0

    metrics["consensus_buy_count"] = len(consensus_buys)
    metrics["consensus_buy_accuracy"] = round(buy_accuracy, 4)
    metrics["consensus_buy_avg_excess"] = round(float(avg_excess_when_buy) * 100, 2)
    metrics["strong_buy_count"] = len(strong_buys)
    metrics["strong_buy_accuracy"] = round(strong_buy_accuracy, 4)
    metrics["strong_buy_avg_excess"] = round(float(avg_excess_strong) * 100, 2)
    metrics["avoid_count"] = len(avoids)
    metrics["avoid_accuracy"] = round(avoid_accuracy, 4)

    signal_dist = {}
    for p in all_preds:
        signal_dist[p["signal"]] = signal_dist.get(p["signal"], 0) + 1
    metrics["signal_distribution"] = signal_dist

    return metrics, all_preds


def train_model(months_history: int = 12) -> dict:
    """Train XGBoost + LightGBM and ensemble approaches, compare all 6, select best.
    
    Approaches compared:
    1. XGBoost alone
    2. LightGBM alone
    3. Simple average (50/50)
    4. Weighted average (walk-forward optimized)
    5. Meta-learner stacking (LogisticRegression/Ridge on model outputs)
    6. Specialized ensemble (XGB classifier + LGB regressor with consensus signals)
    
    Returns dict with training metrics for the selected approach.
    """
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression, Ridge

    _ensure_dirs()

    df = _build_dataset()
    if df.empty or len(df) < 50:
        return {"error": "Insufficient training data", "samples": len(df)}

    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.sort_values("date").reset_index(drop=True)

    # Fill NaN features with median and SAVE medians for prediction-time consistency
    feature_medians = {}
    for col in BASE_FEATURE_COLS:
        if col in df.columns:
            med = df[col].median()
            feature_medians[col] = float(med) if pd.notna(med) else 0.0
            df[col] = df[col].fillna(feature_medians[col])
        else:
            feature_medians[col] = 0.0
            df[col] = 0.0

    # Remove constant features
    active_base = [col for col in BASE_FEATURE_COLS if df[col].std() > 0.01]

    # Add engineered features
    df["rsi_x_regime_bull"] = df["rsi"] * df["market_regime_bull"]
    df["momentum_proxy"] = df["ma50_ratio"] * df["technicals_pct"]
    df["value_momentum"] = df["valuation_pct"] * df["ma50_ratio"]
    df["tech_x_growth"] = df["technicals_pct"] * df["growth_pct"] / 100
    df["rsi_oversold"] = (df["rsi"] < 30).astype(float)
    df["rsi_overbought"] = (df["rsi"] > 70).astype(float)
    df["above_ma200"] = (df["ma200_ratio"] > 1.0).astype(float)
    df["score_rank"] = df.groupby("date")["composite_score"].rank(pct=True)

    active_engineered = [col for col in ENGINEERED_COLS if col in df.columns and df[col].std() > 0.01]
    all_features = active_base + active_engineered

    X = df[all_features].values
    y_cls = df["beat_spy"].values.astype(int)
    y_reg = df["excess_return"].values.astype(float)

    # Class imbalance weight
    neg_count = (y_cls == 0).sum()
    pos_count = (y_cls == 1).sum()
    scale_pos_weight = neg_count / pos_count if pos_count > 0 else 1.0

    # --- Model builders ---
    def xgb_clf_builder():
        return xgb.XGBClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            min_child_weight=3, scale_pos_weight=scale_pos_weight,
            eval_metric="logloss", verbosity=0,
        )

    def xgb_reg_builder():
        return xgb.XGBRegressor(
            n_estimators=200, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            min_child_weight=3, verbosity=0,
        )

    def lgb_clf_builder():
        return lgb.LGBMClassifier(
            num_leaves=31, learning_rate=0.05, n_estimators=200,
            min_child_samples=20, subsample=0.8, colsample_bytree=0.8,
            class_weight="balanced", verbosity=-1,
        )

    def lgb_reg_builder():
        return lgb.LGBMRegressor(
            num_leaves=31, learning_rate=0.05, n_estimators=200,
            min_child_samples=20, subsample=0.8, colsample_bytree=0.8,
            verbosity=-1,
        )

    # --- Walk-forward ensemble evaluation ---
    logger.info("Walk-forward validation: all 5 approaches...")
    wf_results, opt_w_xgb = _walk_forward_ensemble(
        df, X, y_cls, y_reg, all_features, months_history,
        xgb_clf_builder, xgb_reg_builder, lgb_clf_builder, lgb_reg_builder,
    )

    # --- Specialized ensemble evaluation ---
    logger.info("Walk-forward validation: specialized ensemble (XGB clf + LGB reg)...")
    spec_metrics, spec_preds = _walk_forward_specialized(
        df, X, y_cls, y_reg, all_features, months_history,
        xgb_clf_builder, lgb_reg_builder,
    )

    # Compute metrics for all approaches
    def _score(m):
        return (m.get("accuracy", 0) * 0.3 + m.get("f1", 0) * 0.3 +
                m.get("recall", 0) * 0.2 + m.get("regression_corr", 0) * 0.2)

    all_metrics = {}
    all_scores = {}
    for name, r in wf_results.items():
        m = _compute_metrics(r["cls"], r["cls_act"], r["reg"], r["reg_act"], total_samples=len(df))
        all_metrics[name] = m
        all_scores[name] = _score(m)

    # Add specialized ensemble
    if spec_metrics:
        all_metrics["specialized_ensemble"] = spec_metrics
        all_scores["specialized_ensemble"] = _score(spec_metrics)

    # Select best approach
    selected = max(all_scores, key=all_scores.get)
    logger.info("Composite scores: " + ", ".join(f"{k}={v:.4f}" for k, v in sorted(all_scores.items(), key=lambda x: -x[1])))
    logger.info(f"Selected approach: {selected}")

    # --- Train final models on all data ---
    xgb_clf_final = xgb_clf_builder(); xgb_clf_final.fit(X, y_cls)
    xgb_reg_final = xgb_reg_builder(); xgb_reg_final.fit(X, y_reg)
    lgb_clf_final = lgb_clf_builder(); lgb_clf_final.fit(X, y_cls)
    lgb_reg_final = lgb_reg_builder(); lgb_reg_final.fit(X, y_reg)

    # Train meta-learner on full data outputs
    xgb_cls_probs_full = xgb_clf_final.predict_proba(X)[:, 1]
    lgb_cls_probs_full = lgb_clf_final.predict_proba(X)[:, 1]
    xgb_reg_preds_full = xgb_reg_final.predict(X)
    lgb_reg_preds_full = lgb_reg_final.predict(X)

    meta_X_cls = np.column_stack([xgb_cls_probs_full, lgb_cls_probs_full])
    meta_X_reg = np.column_stack([xgb_reg_preds_full, lgb_reg_preds_full])

    meta_clf = LogisticRegression(C=1.0, solver="lbfgs", max_iter=200)
    meta_clf.fit(meta_X_cls, y_cls)

    meta_reg = Ridge(alpha=1.0)
    meta_reg.fit(meta_X_reg, y_reg)

    # Feature importances (from XGBoost as primary)
    feat_imp = dict(zip(all_features, [float(x) for x in xgb_clf_final.feature_importances_]))
    feat_imp_sorted = dict(sorted(feat_imp.items(), key=lambda x: x[1], reverse=True))

    selected_metrics = all_metrics[selected].copy()
    selected_metrics["feature_importances"] = feat_imp_sorted
    selected_metrics["trained_at"] = datetime.now().isoformat()
    selected_metrics["active_model"] = selected
    selected_metrics["ensemble_weight_xgb"] = opt_w_xgb

    # Save ensemble results
    ensemble_results = {
        "approaches": {},
        "composite_scores": {k: round(v, 4) for k, v in all_scores.items()},
        "selected": selected,
        "optimized_weight_xgb": opt_w_xgb,
        "optimized_weight_lgb": round(1 - opt_w_xgb, 4),
        "compared_at": datetime.now().isoformat(),
    }
    for name, m in all_metrics.items():
        ensemble_results["approaches"][name] = {k: v for k, v in m.items() if k != "feature_importances"}
    with open(ENSEMBLE_PATH, "w") as f:
        json.dump(ensemble_results, f, indent=2)

    # Save specialized ensemble results
    if spec_metrics:
        # Compare consensus buys vs simple_avg buys
        simple_avg_r = wf_results.get("simple_avg", {})
        simple_avg_buy_acc = None
        if simple_avg_r.get("cls") and simple_avg_r.get("cls_act"):
            sa_buys = [(p, a) for p, a in zip(simple_avg_r["cls"], simple_avg_r["cls_act"]) if p == 1]
            if sa_buys:
                simple_avg_buy_acc = round(sum(1 for _, a in sa_buys if a == 1) / len(sa_buys), 4)

        spec_results = {
            "specialized_ensemble_metrics": spec_metrics,
            "comparison_vs_simple_avg": {
                "specialized_consensus_buy_accuracy": spec_metrics.get("consensus_buy_accuracy"),
                "specialized_consensus_buy_avg_excess_pct": spec_metrics.get("consensus_buy_avg_excess"),
                "simple_avg_buy_accuracy": simple_avg_buy_acc,
                "specialized_strong_buy_accuracy": spec_metrics.get("strong_buy_accuracy"),
                "specialized_avoid_accuracy": spec_metrics.get("avoid_accuracy"),
            },
            "signal_distribution": spec_metrics.get("signal_distribution", {}),
            "composite_score": round(all_scores.get("specialized_ensemble", 0), 4),
            "all_composite_scores": {k: round(v, 4) for k, v in sorted(all_scores.items(), key=lambda x: -x[1])},
            "selected_overall": selected,
            "evaluated_at": datetime.now().isoformat(),
        }
        with open(SPECIALIZED_ENSEMBLE_PATH, "w") as f:
            json.dump(spec_results, f, indent=2)

    # Save comparison (backward compat)
    comparison = {
        "xgboost": {k: v for k, v in all_metrics["xgboost"].items() if k != "feature_importances"},
        "lightgbm": {k: v for k, v in all_metrics["lightgbm"].items() if k != "feature_importances"},
        "xgboost_composite_score": round(all_scores["xgboost"], 4),
        "lightgbm_composite_score": round(all_scores["lightgbm"], 4),
        "selected_model": selected,
        "compared_at": datetime.now().isoformat(),
    }
    with open(COMPARISON_PATH, "w") as f:
        json.dump(comparison, f, indent=2)

    # Save model artifact with all models for ensemble prediction
    model_artifact = {
        "xgb_classifier": xgb_clf_final,
        "xgb_regressor": xgb_reg_final,
        "lgb_classifier": lgb_clf_final,
        "lgb_regressor": lgb_reg_final,
        "meta_classifier": meta_clf,
        "meta_regressor": meta_reg,
        "ensemble_weight_xgb": opt_w_xgb,
        # Backward compat: classifier/regressor point to best single or are used by ensemble
        "classifier": xgb_clf_final if selected == "xgboost" else lgb_clf_final,
        "regressor": xgb_reg_final if selected == "xgboost" else lgb_reg_final,
        # Specialized ensemble: XGB classifier + LGB regressor
        "spec_xgb_classifier": xgb_clf_final,
        "spec_lgb_regressor": lgb_reg_final,
        "feature_cols": all_features,
        "feature_medians": feature_medians,
        "metrics": selected_metrics,
        "active_model": selected,
        "trained_at": datetime.now().isoformat(),
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model_artifact, f)

    with open(METRICS_PATH, "w") as f:
        json.dump({k: v for k, v in selected_metrics.items() if k != "feature_importances"}, f, indent=2)

    logger.info(f"Model trained ({selected}). Accuracy: {selected_metrics.get('accuracy', 'N/A')}, samples: {len(df)}")
    return selected_metrics


def _load_model() -> Optional[dict]:
    if not MODEL_PATH.exists():
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predict_scores(tickers: Optional[List[str]] = None) -> List[dict]:
    """Predict ML scores for current stocks.
    
    If tickers is None, uses the latest scan results.
    """
    model = _load_model()
    if model is None:
        return [{"error": "Model not trained. Call train_model() first."}]

    active_model = model.get("active_model", "xgboost")

    # Load current scan results
    results_file = DATA_DIR / "scan_results.json"
    if not results_file.exists():
        return [{"error": "No scan results found"}]

    scan = json.loads(results_file.read_text())
    stocks = scan.get("top", scan.get("stocks", []))
    regime_info = scan.get("market_regime", {})
    regime = regime_info.get("regime", "sideways") if isinstance(regime_info, dict) else "sideways"

    if tickers:
        stocks = [s for s in stocks if s["ticker"] in tickers]

    feature_cols = model.get("feature_cols", BASE_FEATURE_COLS)
    feature_medians = model.get("feature_medians", {})

    predictions = []
    for stock in stocks:
        feats = _extract_features_from_stock(stock, regime)
        # Add engineered features (use median fallback instead of hardcoded values)
        rsi_med = feature_medians.get("rsi", 50)
        ma50r_med = feature_medians.get("ma50_ratio", 1.0)
        tech_med = feature_medians.get("technicals_pct", 50)
        val_med = feature_medians.get("valuation_pct", 50)
        growth_med = feature_medians.get("growth_pct", 50)
        
        rsi_val = feats.get("rsi") if feats.get("rsi") is not None else rsi_med
        ma50r_val = feats.get("ma50_ratio") if feats.get("ma50_ratio") is not None else ma50r_med
        tech_val = feats.get("technicals_pct") if feats.get("technicals_pct") is not None else tech_med
        val_val = feats.get("valuation_pct") if feats.get("valuation_pct") is not None else val_med
        growth_val = feats.get("growth_pct") if feats.get("growth_pct") is not None else growth_med
        ma200r_val = feats.get("ma200_ratio") if feats.get("ma200_ratio") is not None else feature_medians.get("ma200_ratio", 1.0)
        
        feats["rsi_x_regime_bull"] = rsi_val * (feats.get("market_regime_bull") or 0)
        feats["momentum_proxy"] = ma50r_val * tech_val
        feats["value_momentum"] = val_val * ma50r_val
        feats["tech_x_growth"] = tech_val * growth_val / 100
        feats["rsi_oversold"] = 1.0 if rsi_val < 30 else 0.0
        feats["rsi_overbought"] = 1.0 if rsi_val > 70 else 0.0
        feats["above_ma200"] = 1.0 if ma200r_val > 1.0 else 0.0
        # Compute score_rank as percentile (consistent with training: pct=True across group)
        rank = stock.get("rank", 10)
        total = len(stocks) if stocks else 20
        feats["score_rank"] = 1.0 - (rank / (total + 1))
        
        # Build feature vector using training medians for None values
        feat_values = []
        for col in feature_cols:
            val = feats.get(col)
            if val is None:
                val = feature_medians.get(col, 0)
            feat_values.append(val)

        X = np.array([feat_values])

        # Predict based on active model approach
        if active_model == "specialized_ensemble":
            # Use XGB classifier for probability, LGB regressor for return
            spec_xgb_clf = model.get("spec_xgb_classifier", model.get("xgb_classifier", model["classifier"]))
            spec_lgb_reg = model.get("spec_lgb_regressor", model.get("lgb_regressor", model["regressor"]))
            beat_spy_prob = float(spec_xgb_clf.predict_proba(X)[0][1])
            predicted_return = float(spec_lgb_reg.predict(X)[0])
        elif active_model in ("simple_avg", "weighted_avg", "meta_learner"):
            xgb_clf = model.get("xgb_classifier", model["classifier"])
            lgb_clf = model.get("lgb_classifier")
            xgb_reg = model.get("xgb_regressor", model["regressor"])
            lgb_reg = model.get("lgb_regressor")

            xgb_prob = float(xgb_clf.predict_proba(X)[0][1])
            xgb_ret = float(xgb_reg.predict(X)[0])

            if lgb_clf is not None and lgb_reg is not None:
                lgb_prob = float(lgb_clf.predict_proba(X)[0][1])
                lgb_ret = float(lgb_reg.predict(X)[0])
            else:
                lgb_prob, lgb_ret = xgb_prob, xgb_ret

            if active_model == "simple_avg":
                beat_spy_prob = 0.5 * xgb_prob + 0.5 * lgb_prob
                predicted_return = 0.5 * xgb_ret + 0.5 * lgb_ret
            elif active_model == "weighted_avg":
                w = model.get("ensemble_weight_xgb", 0.5)
                beat_spy_prob = w * xgb_prob + (1 - w) * lgb_prob
                predicted_return = w * xgb_ret + (1 - w) * lgb_ret
            elif active_model == "meta_learner":
                meta_clf = model.get("meta_classifier")
                meta_reg = model.get("meta_regressor")
                if meta_clf is not None and meta_reg is not None:
                    meta_X_cls = np.array([[xgb_prob, lgb_prob]])
                    meta_X_reg = np.array([[xgb_ret, lgb_ret]])
                    beat_spy_prob = float(meta_clf.predict_proba(meta_X_cls)[0][1])
                    predicted_return = float(meta_reg.predict(meta_X_reg)[0])
                else:
                    beat_spy_prob = 0.5 * xgb_prob + 0.5 * lgb_prob
                    predicted_return = 0.5 * xgb_ret + 0.5 * lgb_ret
        else:
            # Single model (xgboost or lightgbm)
            clf = model["classifier"]
            reg = model["regressor"]
            beat_spy_prob = float(clf.predict_proba(X)[0][1])
            predicted_return = float(reg.predict(X)[0])

        # Specialized ensemble: XGB classifier prob + LGB regressor return
        spec_xgb = model.get("spec_xgb_classifier", model.get("xgb_classifier"))
        spec_lgb = model.get("spec_lgb_regressor", model.get("lgb_regressor"))
        if spec_xgb is not None and spec_lgb is not None:
            xgb_beat_spy_prob = float(spec_xgb.predict_proba(X)[0][1])
            lgb_predicted_return = float(spec_lgb.predict(X)[0])
            consensus = _consensus_signal(xgb_beat_spy_prob, lgb_predicted_return)
        else:
            xgb_beat_spy_prob = beat_spy_prob
            lgb_predicted_return = predicted_return
            consensus = "HOLD"

        predictions.append({
            "ticker": stock["ticker"],
            "ml_score": round(beat_spy_prob * 100, 1),
            "beat_spy_probability": round(beat_spy_prob, 3),
            "predicted_excess_return": round(predicted_return * 100, 2),
            "xgb_beat_spy_prob": round(xgb_beat_spy_prob, 3),
            "lgb_predicted_return": round(lgb_predicted_return * 100, 2),
            "consensus_signal": consensus,
            "composite_score": stock.get("composite_score"),
            "entry_signal": stock.get("entry_signal"),
        })

    predictions.sort(key=lambda x: x["ml_score"], reverse=True)
    return predictions


def get_model_metrics() -> dict:
    """Return model metrics including active model and comparison results."""
    result = {}
    if METRICS_PATH.exists():
        result = json.loads(METRICS_PATH.read_text())
    else:
        return {"error": "Model not trained yet. Call train_model() first."}
    if COMPARISON_PATH.exists():
        result["model_comparison"] = json.loads(COMPARISON_PATH.read_text())
    return result


def compare_with_rules() -> dict:
    """Compare ML-based picks vs rule-based picks from current scan."""
    model = _load_model()
    if model is None:
        return {"error": "Model not trained. Call train_model() first."}

    results_file = DATA_DIR / "scan_results.json"
    if not results_file.exists():
        return {"error": "No scan results found"}

    scan = json.loads(results_file.read_text())
    stocks = scan.get("top", scan.get("stocks", []))

    # Get ML predictions
    ml_preds = predict_scores()
    if ml_preds and "error" in ml_preds[0]:
        return ml_preds[0]

    ml_scores = {p["ticker"]: p for p in ml_preds}

    # Rule-based top 10
    rules_top10 = [s["ticker"] for s in stocks[:10]]

    # ML top 10
    ml_top10 = [p["ticker"] for p in ml_preds[:10]]

    overlap = set(rules_top10) & set(ml_top10)

    # BUY signals from rules
    rules_buys = [s["ticker"] for s in stocks if s.get("entry_signal") in ("BUY", "STRONG_BUY")]

    # ML buys (>60% probability of beating SPY)
    ml_buys = [p["ticker"] for p in ml_preds if p["beat_spy_probability"] > 0.6]

    # Consensus signal buys (specialized ensemble)
    consensus_strong_buys = [p["ticker"] for p in ml_preds if p.get("consensus_signal") == "STRONG_BUY"]
    consensus_buys = [p["ticker"] for p in ml_preds if p.get("consensus_signal") in ("BUY", "STRONG_BUY")]
    consensus_avoids = [p["ticker"] for p in ml_preds if p.get("consensus_signal") == "AVOID"]

    return {
        "rules_top10": rules_top10,
        "ml_top10": ml_top10,
        "overlap_top10": list(overlap),
        "overlap_pct": round(len(overlap) / 10 * 100, 1),
        "rules_buys": rules_buys[:20],
        "ml_buys": ml_buys[:20],
        "ml_buy_overlap_with_rules": list(set(rules_buys) & set(ml_buys)),
        "consensus_strong_buys": consensus_strong_buys[:20],
        "consensus_buys": consensus_buys[:20],
        "consensus_avoids": consensus_avoids[:20],
        "comparison": [
            {
                "ticker": t,
                "rules_rank": next((i + 1 for i, s in enumerate(stocks) if s["ticker"] == t), None),
                "ml_rank": next((i + 1 for i, p in enumerate(ml_preds) if p["ticker"] == t), None),
                "composite_score": ml_scores.get(t, {}).get("composite_score"),
                "ml_score": ml_scores.get(t, {}).get("ml_score"),
                "beat_spy_prob": ml_scores.get(t, {}).get("beat_spy_probability"),
                "consensus_signal": ml_scores.get(t, {}).get("consensus_signal"),
                "xgb_beat_spy_prob": ml_scores.get(t, {}).get("xgb_beat_spy_prob"),
                "lgb_predicted_return": ml_scores.get(t, {}).get("lgb_predicted_return"),
            }
            for t in list(dict.fromkeys(rules_top10 + ml_top10))  # ordered unique
        ],
    }
