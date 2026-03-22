"""
Alpha158 Predictor — Qlib-style ML scoring using price/volume features + regime signals.
Replaces the old fundamental-based ML model with Qlib methodology.

Uses:
- 118 Alpha158 features (technical, from OHLCV)
- 29 regime features (VIX, oil, DXY, SPY, QQQ)
- LightGBM (70%) + XGBoost (30%) ensemble
- IC/ICIR evaluation (not accuracy)
- ZScore normalization

Training data: 5yr historical backfill (210K+ samples)
"""

import json
import logging
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MODEL_DIR = DATA_DIR / "alpha158_models"
TRAINING_DATA = DATA_DIR / "alpha158_training.parquet"

# Ensemble weights (LightGBM 70%, XGBoost 30%)
LGB_WEIGHT = 0.7
XGB_WEIGHT = 0.3

# Regime tickers
REGIME_TICKERS = {
    'SPY': 'spy', '^VIX': 'vix', '^TNX': 'tnx',
    'DX-Y.NYB': 'dxy', 'CL=F': 'oil', 'QQQ': 'qqq',
}


def _ensure_dirs():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)


def _download_regime_data(years: int = 5) -> pd.DataFrame:
    """Download macro regime data and compute features."""
    import yfinance as yf
    
    end = datetime.now()
    start = end - timedelta(days=years * 365)
    
    regime_raw = {}
    for ticker, name in REGIME_TICKERS.items():
        try:
            data = yf.download(ticker, start=start.strftime('%Y-%m-%d'),
                             end=end.strftime('%Y-%m-%d'), progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            regime_raw[name] = data['Close']
        except Exception as e:
            logger.warning(f"Failed to download {name}: {e}")
    
    regime_df = pd.DataFrame(regime_raw).ffill().bfill()
    
    # Compute regime features
    features = pd.DataFrame(index=regime_df.index)
    for name in ['spy', 'vix', 'oil', 'dxy', 'qqq']:
        if name not in regime_df:
            continue
        s = regime_df[name]
        features[f'{name}_ma20'] = s / s.rolling(20).mean()
        features[f'{name}_ma60'] = s / s.rolling(60).mean()
        features[f'{name}_ret5'] = s / s.shift(5) - 1
        features[f'{name}_ret20'] = s / s.shift(20) - 1
        features[f'{name}_std20'] = s.pct_change().rolling(20).std()
    
    if 'qqq' in regime_df and 'spy' in regime_df:
        features['tech_rel_20d'] = (regime_df['qqq'] / regime_df['qqq'].shift(20)) / \
                                   (regime_df['spy'] / regime_df['spy'].shift(20)) - 1
    if 'vix' in regime_df:
        features['vix_level'] = regime_df['vix']
        features['vix_regime'] = (regime_df['vix'] > 25).astype(float)
    if 'oil' in regime_df and 'spy' in regime_df:
        features['oil_spy_corr20'] = regime_df['oil'].pct_change().rolling(20).corr(
            regime_df['spy'].pct_change())
    
    features = features.replace([np.inf, -np.inf], np.nan).ffill()
    return features


def train(train_years: int = 5) -> Dict:
    """
    Train Alpha158 LightGBM + XGBoost ensemble model.
    
    Returns dict with training metrics.
    """
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.preprocessing import StandardScaler
    
    _ensure_dirs()
    
    # Load training data
    if not TRAINING_DATA.exists():
        raise FileNotFoundError(f"Training data not found at {TRAINING_DATA}. Run backfill first.")
    
    logger.info("Loading Alpha158 training data...")
    df = pd.read_parquet(TRAINING_DATA)
    df['date'] = pd.to_datetime(df['date'])
    
    # Load and merge regime features
    logger.info("Downloading regime data...")
    regime_features = _download_regime_data(years=train_years)
    if regime_features.index.tz is not None:
        regime_features.index = regime_features.index.tz_localize(None)
    if df['date'].dt.tz is not None:
        df['date'] = df['date'].dt.tz_localize(None)
    
    df = df.merge(regime_features, left_on='date', right_index=True, how='left')
    
    # Feature columns
    label_cols = ['forward_return', 'spy_return', 'excess_return', 'beat_spy']
    meta_cols = ['ticker', 'date']
    feature_cols = [c for c in df.columns if c not in label_cols + meta_cols]
    
    # Temporal split
    df = df.sort_values('date').reset_index(drop=True)
    train_mask = df['date'] < '2025-01-01'
    valid_mask = (df['date'] >= '2025-01-01') & (df['date'] < '2025-07-01')
    test_mask = df['date'] >= '2025-07-01'
    
    train_df = df[train_mask]
    valid_df = df[valid_mask]
    test_df = df[test_mask]
    
    logger.info(f"Train: {len(train_df)} | Valid: {len(valid_df)} | Test: {len(test_df)}")
    logger.info(f"Features: {len(feature_cols)}")
    
    # Prepare data
    X_train = train_df[feature_cols].fillna(0).values
    X_valid = valid_df[feature_cols].fillna(0).values
    X_test = test_df[feature_cols].fillna(0).values
    y_train = train_df['excess_return'].values
    y_valid = valid_df['excess_return'].values
    y_test = test_df['excess_return'].values
    
    # ZScore normalization
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_valid = scaler.transform(X_valid)
    X_test = scaler.transform(X_test)
    
    # ---- Train XGBoost ----
    logger.info("Training XGBoost...")
    dtrain = xgb.DMatrix(X_train, label=y_train)
    dvalid = xgb.DMatrix(X_valid, label=y_valid)
    dtest = xgb.DMatrix(X_test, label=y_test)
    
    xgb_params = {
        'objective': 'reg:squarederror',
        'max_depth': 6, 'eta': 0.05,
        'subsample': 0.85, 'colsample_bytree': 0.85,
        'min_child_weight': 10,
        'reg_alpha': 0.5, 'reg_lambda': 2.0,
        'nthread': 8,
    }
    
    xgb_model = xgb.train(xgb_params, dtrain, num_boost_round=800,
                          evals=[(dvalid, 'valid')], early_stopping_rounds=50,
                          verbose_eval=False)
    
    # ---- Train LightGBM ----
    logger.info("Training LightGBM...")
    lgb_train = lgb.Dataset(X_train, label=y_train)
    lgb_valid = lgb.Dataset(X_valid, label=y_valid, reference=lgb_train)
    
    lgb_params = {
        'objective': 'regression', 'metric': 'rmse',
        'num_leaves': 128, 'learning_rate': 0.05,
        'feature_fraction': 0.85, 'bagging_fraction': 0.85, 'bagging_freq': 5,
        'min_child_samples': 10,
        'reg_alpha': 0.5, 'reg_lambda': 2.0,
        'verbose': -1,
    }
    
    lgb_model = lgb.train(lgb_params, lgb_train, num_boost_round=800,
                          valid_sets=[lgb_valid], callbacks=[lgb.early_stopping(50)])
    
    # ---- Evaluate ----
    pred_xgb_test = xgb_model.predict(dtest)
    pred_lgb_test = lgb_model.predict(X_test)
    pred_ensemble = XGB_WEIGHT * pred_xgb_test + LGB_WEIGHT * pred_lgb_test
    
    def _compute_ic(pred, actual, dates):
        d = pd.DataFrame({'p': pred, 'a': actual, 'd': pd.to_datetime(dates)})
        daily = d.groupby('d', group_keys=False).apply(
            lambda x: pd.Series({'ic': x['p'].corr(x['a'])}) if len(x) > 5 else pd.Series({'ic': np.nan})
        ).dropna()
        ic = daily['ic'].mean() if 'ic' in daily.columns else daily.mean()
        std = daily['ic'].std() if 'ic' in daily.columns else daily.std()
        icir = float(ic / std) if std > 0 else 0
        return float(ic), icir
    
    def _top_bottom(pred, actual, dates, pct=0.1):
        d = pd.DataFrame({'p': pred, 'a': actual, 'd': pd.to_datetime(dates)})
        tops, bots = [], []
        for _, g in d.groupby('d'):
            n = max(1, int(len(g) * pct))
            s = g.sort_values('p', ascending=False)
            tops.append(s['a'].head(n).mean())
            bots.append(s['a'].tail(n).mean())
        return float(np.mean(tops)), float(np.mean(bots))
    
    ic_xgb, icir_xgb = _compute_ic(pred_xgb_test, y_test, test_df['date'].values)
    ic_lgb, icir_lgb = _compute_ic(pred_lgb_test, y_test, test_df['date'].values)
    ic_ens, icir_ens = _compute_ic(pred_ensemble, y_test, test_df['date'].values)
    top_ens, bot_ens = _top_bottom(pred_ensemble, y_test, test_df['date'].values)
    
    metrics = {
        'trained_at': datetime.now().isoformat(),
        'train_samples': len(train_df),
        'valid_samples': len(valid_df),
        'test_samples': len(test_df),
        'features': len(feature_cols),
        'feature_names': feature_cols,
        'xgb_ic': ic_xgb, 'xgb_icir': icir_xgb,
        'lgb_ic': ic_lgb, 'lgb_icir': icir_lgb,
        'ensemble_ic': ic_ens, 'ensemble_icir': icir_ens,
        'ensemble_spread': float(top_ens - bot_ens),
        'top_10pct_excess': top_ens,
        'bottom_10pct_excess': bot_ens,
        'weights': {'xgb': XGB_WEIGHT, 'lgb': LGB_WEIGHT},
    }
    
    logger.info(f"XGB IC: {ic_xgb:.4f} | LGB IC: {ic_lgb:.4f} | Ensemble IC: {ic_ens:.4f}")
    logger.info(f"Spread: {top_ens - bot_ens:.4f}")
    
    # ---- Save ----
    model_data = {
        'xgb_model': xgb_model,
        'lgb_model': lgb_model,
        'scaler': scaler,
        'feature_cols': feature_cols,
        'metrics': metrics,
    }
    
    model_path = MODEL_DIR / "ensemble.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump(model_data, f)
    
    metrics_path = MODEL_DIR / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, default=str))
    
    # Save XGBoost separately for inspection
    xgb_model.save_model(str(MODEL_DIR / "xgb.model"))
    lgb_model.save_model(str(MODEL_DIR / "lgb.model"))
    
    logger.info(f"Models saved to {MODEL_DIR}")
    return metrics


def predict_for_stocks(tickers: Optional[List[str]] = None) -> List[Dict]:
    """
    Predict Alpha158 scores for stocks using current price data.
    
    Downloads recent OHLCV, computes Alpha158 features + regime features,
    runs through ensemble model, returns ranked predictions.
    """
    import yfinance as yf
    from .alpha158 import compute_alpha158_fast
    
    # Load model
    model_path = MODEL_DIR / "ensemble.pkl"
    if not model_path.exists():
        return [{"error": "Alpha158 model not trained. Call train() first."}]
    
    with open(model_path, 'rb') as f:
        model_data = pickle.load(f)
    
    xgb_model = model_data['xgb_model']
    lgb_model = model_data['lgb_model']
    scaler = model_data['scaler']
    feature_cols = model_data['feature_cols']
    
    # Get tickers from scan results if not specified
    if tickers is None:
        scan_file = DATA_DIR / "scan_results.json"
        if scan_file.exists():
            scan = json.loads(scan_file.read_text())
            all_stocks = scan.get("all_scores", scan.get("top", []))
            tickers = [s["ticker"] for s in all_stocks]
        else:
            return [{"error": "No scan results and no tickers specified"}]
    
    if not tickers:
        return []
    
    # Download recent 90 days of OHLCV (need 60 for features + buffer)
    logger.info(f"Downloading OHLCV for {len(tickers)} tickers...")
    end = datetime.now()
    start = end - timedelta(days=120)
    
    all_hist = {}
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            data = yf.download(batch, start=start.strftime('%Y-%m-%d'),
                             end=end.strftime('%Y-%m-%d'), progress=False, threads=True)
            if isinstance(data.columns, pd.MultiIndex):
                available = data.columns.get_level_values(1).unique()
                for t in batch:
                    if t in available:
                        try:
                            df = data.xs(t, level=1, axis=1).dropna(how='all')
                            if len(df) >= 60:
                                all_hist[t] = df
                        except Exception:
                            pass
            elif len(batch) == 1 and not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                all_hist[batch[0]] = data.dropna(how='all')
            
            if i + batch_size < len(tickers):
                time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Batch download failed: {e}")
    
    logger.info(f"Got OHLCV for {len(all_hist)} tickers")
    
    # Download regime data (just recent, not 5yr)
    regime_features = _download_regime_data(years=1)
    if regime_features.index.tz is not None:
        regime_features.index = regime_features.index.tz_localize(None)
    
    # Get latest regime feature values
    latest_regime = regime_features.iloc[-1].to_dict() if not regime_features.empty else {}
    
    # Compute Alpha158 features for each stock
    predictions = []
    alpha158_feature_cols = [c for c in feature_cols if not any(
        c.startswith(prefix) for prefix in ['spy_', 'vix_', 'tnx_', 'dxy_', 'oil_', 'qqq_', 
                                            'tech_rel', 'vix_level', 'vix_regime', 'oil_spy']
    )]
    regime_feature_cols = [c for c in feature_cols if c not in alpha158_feature_cols]
    
    for ticker in tickers:
        if ticker not in all_hist:
            continue
        
        try:
            hist = all_hist[ticker]
            features = compute_alpha158_fast(hist)
            
            if features.empty:
                continue
            
            # Get latest features
            latest = features.iloc[-1].to_dict()
            
            # Build full feature vector
            feat_values = []
            for col in feature_cols:
                if col in latest:
                    val = latest[col]
                elif col in latest_regime:
                    val = latest_regime[col]
                else:
                    val = 0
                feat_values.append(val if pd.notna(val) else 0)
            
            X = np.array([feat_values])
            X = scaler.transform(X)
            
            # Predict
            import xgboost as xgb_lib
            dmatrix = xgb_lib.DMatrix(X)
            pred_xgb = float(xgb_model.predict(dmatrix)[0])
            pred_lgb = float(lgb_model.predict(X)[0])
            pred_ensemble = XGB_WEIGHT * pred_xgb + LGB_WEIGHT * pred_lgb
            
            predictions.append({
                'ticker': ticker,
                'alpha158_score': round(pred_ensemble * 100, 2),  # excess return prediction (%)
                'xgb_pred': round(pred_xgb * 100, 2),
                'lgb_pred': round(pred_lgb * 100, 2),
                'predicted_excess_return': round(pred_ensemble * 100, 2),
            })
        except Exception as e:
            logger.warning(f"Failed to predict {ticker}: {e}")
    
    # Rank by predicted excess return
    predictions.sort(key=lambda x: x['alpha158_score'], reverse=True)
    
    for i, p in enumerate(predictions):
        p['rank'] = i + 1
        total = len(predictions)
        p['percentile'] = round((1 - i / total) * 100, 1) if total > 0 else 50
    
    logger.info(f"Alpha158 predictions for {len(predictions)} stocks")
    return predictions


def get_metrics() -> Dict:
    """Return current model metrics."""
    metrics_path = MODEL_DIR / "metrics.json"
    if metrics_path.exists():
        return json.loads(metrics_path.read_text())
    return {"error": "Model not trained yet"}
