#!/usr/bin/env python3
"""Debug, diagnose, and tune the ML model."""

import json
import logging
import os
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

DATA_DIR = Path(__file__).parent / "data"
ML_DIR = DATA_DIR / "ml"
ML_DIR.mkdir(parents=True, exist_ok=True)

# ─── Step 1: Diagnose ───────────────────────────────────────────────
print("=" * 60)
print("STEP 1: DIAGNOSIS")
print("=" * 60)

from src.ml_model import _build_dataset, FEATURE_COLS

df = _build_dataset()
print(f"\nDataset size: {len(df)} samples")
print(f"Date range: {df['date'].min()} to {df['date'].max()}")
print(f"Unique dates: {df['date'].nunique()}")
print(f"Unique tickers: {df['ticker'].nunique()}")

# Class balance
beat_counts = df['beat_spy'].value_counts()
print(f"\nClass balance:")
print(f"  Beat SPY (1): {beat_counts.get(1, 0)} ({beat_counts.get(1, 0)/len(df)*100:.1f}%)")
print(f"  Didn't (0):   {beat_counts.get(0, 0)} ({beat_counts.get(0, 0)/len(df)*100:.1f}%)")

# Feature distributions
print(f"\nFeature distributions:")
for col in FEATURE_COLS:
    if col in df.columns:
        vals = df[col].dropna()
        nunique = vals.nunique()
        print(f"  {col:25s}: mean={vals.mean():7.2f}  std={vals.std():7.2f}  min={vals.min():7.2f}  max={vals.max():7.2f}  unique={nunique}")

# Identify problem features
print("\n⚠️  PROBLEM FEATURES (constant or near-constant):")
for col in FEATURE_COLS:
    if col in df.columns:
        if df[col].std() < 0.01:
            print(f"  {col}: std={df[col].std():.4f} — CONSTANT!")

# ─── Step 2: Run baseline ────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2: BASELINE (current config)")
print("=" * 60)

from src.ml_model import train_model
baseline_metrics = train_model()
print(f"\nBaseline metrics:")
for k, v in baseline_metrics.items():
    if k != 'feature_importances':
        print(f"  {k}: {v}")
print(f"\nFeature importances:")
for feat, imp in baseline_metrics.get('feature_importances', {}).items():
    print(f"  {feat:25s}: {imp:.4f} {'⚠️ ZERO' if imp == 0 else ''}")

# ─── Step 3: Fix data issues & tune ────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3: FIX DATA + TUNE")
print("=" * 60)

# Prepare clean dataset - remove constant features, add engineered ones
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)

# Fill NaN
for col in FEATURE_COLS:
    if col in df.columns:
        df[col] = df[col].fillna(df[col].median())
    else:
        df[col] = 0.0

# Remove constant features
constant_feats = [col for col in FEATURE_COLS if df[col].std() < 0.01]
print(f"Removing constant features: {constant_feats}")
active_features = [col for col in FEATURE_COLS if col not in constant_feats]

# Add interaction features
df["rsi_x_regime_bull"] = df["rsi"] * df["market_regime_bull"]
df["momentum_proxy"] = df["ma50_ratio"] * df["technicals_pct"]
df["value_momentum"] = df["valuation_pct"] * df["ma50_ratio"]
df["tech_x_growth"] = df["technicals_pct"] * df["growth_pct"] / 100
df["rsi_oversold"] = (df["rsi"] < 30).astype(float)
df["rsi_overbought"] = (df["rsi"] > 70).astype(float)
df["above_ma200"] = (df["ma200_ratio"] > 1.0).astype(float)
df["score_rank"] = df.groupby("date")["composite_score"].rank(pct=True)

interaction_features = [
    "rsi_x_regime_bull", "momentum_proxy", "value_momentum", "tech_x_growth",
    "rsi_oversold", "rsi_overbought", "above_ma200", "score_rank"
]
enhanced_features = active_features + interaction_features

X = df[enhanced_features].values
y_cls = df["beat_spy"].values.astype(int)
dates = sorted(df["date"].unique())
n_dates = len(dates)

print(f"Enhanced features: {len(enhanced_features)}")
print(f"Active features: {enhanced_features}")

# ─── Walk-forward tuning ────────────────────────────────────────────
import xgboost as xgb
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.ensemble import RandomForestClassifier

def walk_forward_eval(model_fn, X_all, y_all, df_ref, dates_list, train_window=12):
    """Walk-forward cross-validation."""
    preds_all, actuals_all = [], []
    for i in range(train_window, len(dates_list)):
        train_dates = dates_list[max(0, i - train_window):i]
        test_date = dates_list[i]
        train_mask = df_ref["date"].isin(train_dates)
        test_mask = df_ref["date"] == test_date
        X_tr, y_tr = X_all[train_mask], y_all[train_mask]
        X_te, y_te = X_all[test_mask], y_all[test_mask]
        if len(X_tr) < 10 or len(X_te) == 0:
            continue
        model = model_fn()
        model.fit(X_tr, y_tr)
        preds_all.extend(model.predict(X_te))
        actuals_all.extend(y_te)
    if not preds_all:
        return {}
    return {
        "accuracy": round(accuracy_score(actuals_all, preds_all), 4),
        "precision": round(precision_score(actuals_all, preds_all, zero_division=0), 4),
        "recall": round(recall_score(actuals_all, preds_all, zero_division=0), 4),
        "f1": round(f1_score(actuals_all, preds_all, zero_division=0), 4),
        "n_samples": len(preds_all),
    }

# Class imbalance ratio for scale_pos_weight
neg_count = (y_cls == 0).sum()
pos_count = (y_cls == 1).sum()
scale_pos = neg_count / pos_count if pos_count > 0 else 1.0
print(f"\nscale_pos_weight: {scale_pos:.2f}")

# Configurations to try
configs = {
    "xgb_default": lambda: xgb.XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8, eval_metric="logloss", verbosity=0,
    ),
    "xgb_balanced": lambda: xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, scale_pos_weight=scale_pos,
        min_child_weight=3, eval_metric="logloss", verbosity=0,
    ),
    "xgb_deep": lambda: xgb.XGBClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.03,
        subsample=0.7, colsample_bytree=0.7, scale_pos_weight=scale_pos,
        min_child_weight=5, gamma=0.1, eval_metric="logloss", verbosity=0,
    ),
    "xgb_shallow": lambda: xgb.XGBClassifier(
        n_estimators=150, max_depth=3, learning_rate=0.1,
        subsample=0.9, colsample_bytree=0.9, scale_pos_weight=scale_pos,
        min_child_weight=1, eval_metric="logloss", verbosity=0,
    ),
    "xgb_aggressive_recall": lambda: xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, scale_pos_weight=scale_pos * 1.5,
        min_child_weight=2, eval_metric="logloss", verbosity=0,
    ),
    "random_forest": lambda: RandomForestClassifier(
        n_estimators=200, max_depth=6, class_weight="balanced",
        min_samples_leaf=5, random_state=42,
    ),
}

# Try LightGBM
try:
    import lightgbm as lgb
    configs["lgbm_balanced"] = lambda: lgb.LGBMClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, scale_pos_weight=scale_pos,
        min_child_weight=3, verbosity=-1,
    )
    configs["lgbm_tuned"] = lambda: lgb.LGBMClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.03,
        subsample=0.7, colsample_bytree=0.7, scale_pos_weight=scale_pos * 1.3,
        min_child_weight=5, num_leaves=31, verbosity=-1,
    )
    print("LightGBM available ✓")
except ImportError:
    print("LightGBM not installed, skipping")

print("\n" + "-" * 60)
print("WALK-FORWARD EVALUATION RESULTS")
print("-" * 60)

results = {}
best_name, best_f1 = None, -1
for name, model_fn in configs.items():
    t0 = time.time()
    metrics = walk_forward_eval(model_fn, X, y_cls, df, dates, train_window=12)
    elapsed = time.time() - t0
    metrics["time_s"] = round(elapsed, 1)
    results[name] = metrics
    f1 = metrics.get("f1", 0)
    print(f"\n{name}:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    if f1 > best_f1:
        best_f1 = f1
        best_name = name

print(f"\n{'='*60}")
print(f"BEST MODEL: {best_name} (F1={best_f1})")
print(f"{'='*60}")

# ─── Step 4: Save results ──────────────────────────────────────────
tuning_results = {
    "timestamp": datetime.now().isoformat(),
    "dataset_size": len(df),
    "class_balance": {"beat_spy": int(pos_count), "didnt": int(neg_count)},
    "constant_features_removed": constant_feats,
    "interaction_features_added": interaction_features,
    "enhanced_feature_count": len(enhanced_features),
    "baseline_metrics": {k: v for k, v in baseline_metrics.items() if k != "feature_importances"},
    "tuning_results": results,
    "best_model": best_name,
    "best_metrics": results.get(best_name, {}),
}

with open(ML_DIR / "tuning_results.json", "w") as f:
    json.dump(tuning_results, f, indent=2, default=str)

print(f"\nResults saved to data/ml/tuning_results.json")

# ─── Step 5: Comparison ────────────────────────────────────────────
print(f"\n{'='*60}")
print("BEFORE vs AFTER COMPARISON")
print(f"{'='*60}")
baseline = tuning_results["baseline_metrics"]
best = results.get(best_name, {})
for metric in ["accuracy", "precision", "recall", "f1"]:
    b = baseline.get(metric, "N/A")
    a = best.get(metric, "N/A")
    if isinstance(b, (int, float)) and isinstance(a, (int, float)):
        delta = a - b
        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
        print(f"  {metric:12s}: {b:.4f} → {a:.4f}  ({arrow} {delta:+.4f})")
    else:
        print(f"  {metric:12s}: {b} → {a}")
