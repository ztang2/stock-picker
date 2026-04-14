"""Machine learning model endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..ml_model import (
    train_model as _ml_train,
    predict_scores as _ml_predict,
    get_model_metrics as _ml_metrics,
    compare_with_rules as _ml_compare,
)
from .deps import logger

router = APIRouter(tags=["ml"])


@router.get("/ml/train")
def ml_train(months_history: int = Query(12, ge=1, le=36)):
    """Train ML model."""
    try:
        return _ml_train(months_history=months_history)
    except Exception as e:
        logger.error("ML training failed", exc_info=True)
        raise HTTPException(500, f"ML training failed: {e}")


@router.get("/ml/predict")
def ml_predict(tickers: Optional[str] = Query(None, description="Comma-separated tickers")):
    """Get ML predictions for stocks."""
    try:
        ticker_list = (
            [t.strip().upper() for t in tickers.split(",")] if tickers else None
        )
        return {"predictions": _ml_predict(ticker_list)}
    except Exception as e:
        raise HTTPException(500, f"ML prediction failed: {e}")


@router.get("/ml/metrics")
def ml_metrics():
    """Get ML model metrics."""
    return _ml_metrics()


@router.get("/ml/compare")
def ml_compare():
    """Compare ML vs rule-based picks."""
    try:
        return _ml_compare()
    except Exception as e:
        raise HTTPException(500, f"ML comparison failed: {e}")


@router.get("/alpha158/train")
def alpha158_train():
    """Train Alpha158 Qlib-style ML model."""
    try:
        from ..alpha158_predictor import train as a158_train

        return a158_train()
    except Exception as e:
        raise HTTPException(500, f"Alpha158 training failed: {e}")


@router.get("/alpha158/predict")
def alpha158_predict(n: int = Query(20)):
    """Predict Alpha158 scores for top N stocks."""
    try:
        from ..alpha158_predictor import predict_for_stocks

        return predict_for_stocks()[:n]
    except Exception as e:
        raise HTTPException(500, f"Alpha158 prediction failed: {e}")


@router.get("/alpha158/metrics")
def alpha158_metrics():
    """Get Alpha158 model metrics."""
    from ..alpha158_predictor import get_metrics

    return get_metrics()
