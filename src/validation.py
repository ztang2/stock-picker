"""Daily prediction validation — track what we predicted vs what actually happened.

Each day after market close:
1. Load yesterday's scan results (predictions)
2. Check actual price changes today
3. Score: did BUY stocks outperform HOLD/WAIT? Did scores predict returns?
4. Log results for ongoing accuracy tracking

This is the ground truth layer — everything else is theory until validated here.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VALIDATION_LOG = DATA_DIR / "validation_log.json"
ML_VALIDATION_LOG = DATA_DIR / "ml_validation_log.json"
ML_WEIGHT_STATE = DATA_DIR / "ml_weight_state.json"
RESULTS_FILE = DATA_DIR / "scan_results.json"
PREV_RESULTS_FILE = DATA_DIR / "prev_scan_results.json"


def _load_json(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None


def _save_json(path: Path, data):
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def validate_predictions(
    prev_results: Optional[dict] = None,
    current_prices: Optional[Dict[str, float]] = None,
) -> dict:
    """Compare yesterday's predictions with today's actual prices.
    
    Args:
        prev_results: Yesterday's scan results. Loads from file if None.
        current_prices: {ticker: current_price}. Fetches via yfinance if None.
    
    Returns:
        Validation report dict
    """
    if prev_results is None:
        prev_results = _load_json(PREV_RESULTS_FILE)
    
    if not prev_results or not prev_results.get("top"):
        return {"error": "No previous results to validate"}
    
    prev_top = prev_results["top"]
    prev_timestamp = prev_results.get("timestamp", "unknown")
    
    # Get current prices
    if current_prices is None:
        current_prices = _fetch_current_prices([s["ticker"] for s in prev_top])
    
    if not current_prices:
        return {"error": "Could not fetch current prices"}
    
    # Fetch SPY for benchmark
    spy_price_prev = None
    spy_price_now = None
    try:
        import yfinance as yf
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="5d")
        if len(spy_hist) >= 2:
            spy_price_prev = float(spy_hist["Close"].iloc[-2])
            spy_price_now = float(spy_hist["Close"].iloc[-1])
    except Exception:
        pass
    
    spy_return = None
    if spy_price_prev and spy_price_now:
        spy_return = (spy_price_now - spy_price_prev) / spy_price_prev * 100
    
    # Validate each prediction (including ML predictions)
    results_by_signal = {"BUY": [], "STRONG_BUY": [], "HOLD": [], "WAIT": []}
    ml_predictions = []
    all_results = []
    
    for stock in prev_top:
        ticker = stock.get("ticker")
        if ticker not in current_prices:
            continue
        
        prev_price = stock.get("current_price") or stock.get("price")
        if not prev_price:
            continue
        
        curr_price = current_prices[ticker]
        daily_return = (curr_price - prev_price) / prev_price * 100
        alpha = daily_return - spy_return if spy_return is not None else None
        
        signal = stock.get("entry_signal", "HOLD")
        score = stock.get("composite_score", 0)
        ml_score = stock.get("ml_score")
        ml_signal = stock.get("ml_signal")
        
        result = {
            "ticker": ticker,
            "signal": signal,
            "score": score,
            "ml_score": ml_score,
            "ml_signal": ml_signal,
            "prev_price": round(prev_price, 2),
            "curr_price": round(curr_price, 2),
            "return_pct": round(daily_return, 3),
            "alpha": round(alpha, 3) if alpha is not None else None,
            "beat_spy": daily_return > spy_return if spy_return is not None else None,
        }
        
        all_results.append(result)
        if signal in results_by_signal:
            results_by_signal[signal].append(result)
        
        # Track ML predictions separately
        if ml_score is not None and ml_signal is not None:
            ml_predictions.append({
                "ticker": ticker,
                "ml_score": ml_score,
                "ml_signal": ml_signal,
                "return_pct": round(daily_return, 3),
                "beat_spy": daily_return > spy_return if spy_return is not None else None,
            })
    
    # Compute signal group stats
    signal_stats = {}
    for signal, group in results_by_signal.items():
        if not group:
            continue
        returns = [r["return_pct"] for r in group]
        alphas = [r["alpha"] for r in group if r["alpha"] is not None]
        beats = [r["beat_spy"] for r in group if r["beat_spy"] is not None]
        
        signal_stats[signal] = {
            "count": len(group),
            "avg_return": round(sum(returns) / len(returns), 3),
            "avg_alpha": round(sum(alphas) / len(alphas), 3) if alphas else None,
            "beat_spy_rate": round(sum(beats) / len(beats) * 100, 1) if beats else None,
        }
    
    # Key question: did BUY outperform HOLD?
    buy_avg = signal_stats.get("BUY", {}).get("avg_return")
    hold_avg = signal_stats.get("HOLD", {}).get("avg_return")
    signal_useful = None
    if buy_avg is not None and hold_avg is not None:
        signal_useful = buy_avg > hold_avg
    
    # Score-return correlation
    score_return_corr = None
    if len(all_results) >= 5:
        try:
            scores = [r["score"] for r in all_results]
            returns = [r["return_pct"] for r in all_results]
            df = pd.DataFrame({"score": scores, "return": returns})
            score_return_corr = round(float(df["score"].corr(df["return"])), 3)
        except Exception:
            pass
    
    # ML-specific validation
    ml_accuracy = None
    ml_avg_return = None
    if ml_predictions:
        ml_correct = sum(1 for p in ml_predictions if p["beat_spy"])
        ml_accuracy = round(ml_correct / len(ml_predictions) * 100, 1)
        ml_avg_return = round(sum(p["return_pct"] for p in ml_predictions) / len(ml_predictions), 3)
        
        # Track ML predictions in separate log
        ml_report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "prev_scan_timestamp": prev_timestamp,
            "spy_return": round(spy_return, 3) if spy_return is not None else None,
            "ml_accuracy": ml_accuracy,
            "ml_avg_return": ml_avg_return,
            "ml_predictions_count": len(ml_predictions),
            "predictions": ml_predictions,
        }
        
        ml_log = _load_json(ML_VALIDATION_LOG) or []
        ml_log.append(ml_report)
        _save_json(ML_VALIDATION_LOG, ml_log[-90:])
        
        # Check for consecutive weeks of poor ML performance
        _check_ml_performance_and_adjust(ml_log)
    
    report = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "prev_scan_timestamp": prev_timestamp,
        "spy_return": round(spy_return, 3) if spy_return is not None else None,
        "stocks_validated": len(all_results),
        "signal_stats": signal_stats,
        "signal_useful": signal_useful,
        "score_return_correlation": score_return_corr,
        "ml_accuracy": ml_accuracy,
        "ml_avg_return": ml_avg_return,
        "details": all_results,
    }
    
    # Append to log
    log = _load_json(VALIDATION_LOG) or []
    log.append(report)
    _save_json(VALIDATION_LOG, log[-90:])  # Keep 90 days
    
    return report


def _fetch_current_prices(tickers: List[str]) -> Dict[str, float]:
    """Fetch current prices for a list of tickers (batch download)."""
    prices = {}
    try:
        import yfinance as yf
        # Batch download instead of N+1 individual requests
        data = yf.download(tickers, period="2d", progress=False, threads=True)
        if data is not None and not data.empty:
            close = data["Close"]
            if isinstance(close, pd.Series):
                # Single ticker
                if len(close) >= 1:
                    prices[tickers[0]] = float(close.iloc[-1])
            else:
                for ticker in tickers:
                    if ticker in close.columns:
                        val = close[ticker].iloc[-1]
                        if pd.notna(val):
                            prices[ticker] = float(val)
    except Exception:
        pass
    return prices


def get_validation_summary(days: int = 7) -> dict:
    """Get summary of recent validation results (including ML accuracy)."""
    log = _load_json(VALIDATION_LOG) or []
    recent = log[-days:]
    
    if not recent:
        return {"error": "No validation data yet", "days_available": 0}
    
    # Aggregate rule-based signals
    total_buy_correct = 0
    total_buy_count = 0
    total_signal_useful = 0
    total_signal_checks = 0
    correlations = []
    ml_accuracies = []
    
    for day in recent:
        buy_stats = day.get("signal_stats", {}).get("BUY", {})
        if buy_stats.get("beat_spy_rate") is not None:
            total_buy_correct += buy_stats["beat_spy_rate"] * buy_stats["count"] / 100
            total_buy_count += buy_stats["count"]
        
        if day.get("signal_useful") is not None:
            total_signal_useful += 1 if day["signal_useful"] else 0
            total_signal_checks += 1
        
        if day.get("score_return_correlation") is not None:
            correlations.append(day["score_return_correlation"])
        
        if day.get("ml_accuracy") is not None:
            ml_accuracies.append(day["ml_accuracy"])
    
    # Compute ML accuracy over the period
    ml_avg_accuracy = round(sum(ml_accuracies) / len(ml_accuracies), 1) if ml_accuracies else None
    
    return {
        "days_analyzed": len(recent),
        "buy_beat_spy_rate": round(total_buy_correct / total_buy_count * 100, 1) if total_buy_count > 0 else None,
        "signal_useful_rate": round(total_signal_useful / total_signal_checks * 100, 1) if total_signal_checks > 0 else None,
        "avg_score_correlation": round(sum(correlations) / len(correlations), 3) if correlations else None,
        "ml_avg_accuracy": ml_avg_accuracy,
        "ml_days_tracked": len(ml_accuracies),
        "verdict": _verdict(total_buy_correct, total_buy_count, total_signal_useful, total_signal_checks),
    }


def _check_ml_performance_and_adjust(ml_log: List[dict]):
    """Check ML accuracy over recent weeks and auto-disable if underperforming."""
    if len(ml_log) < 14:  # Need at least 2 weeks of data
        return
    
    # Get last 2 weeks (14 days) of ML accuracy
    recent = ml_log[-14:]
    recent_accuracies = [r["ml_accuracy"] for r in recent if r.get("ml_accuracy") is not None]
    
    if len(recent_accuracies) < 10:  # Need at least 10 days of data
        return
    
    # Check if ML accuracy has been below 50% for multiple consecutive days
    consecutive_poor = 0
    for acc in reversed(recent_accuracies):
        if acc < 50:
            consecutive_poor += 1
        else:
            break
    
    # If ML has been underperforming for 10+ consecutive days, disable it
    if consecutive_poor >= 10:
        logger.warning(f"⚠️ ML ACCURACY ALERT: Below 50% for {consecutive_poor} consecutive days. Auto-disabling ML.")
        
        # Save state to force ML weight to 0
        state = {
            "ml_disabled": True,
            "disabled_at": datetime.now().isoformat(),
            "reason": f"ML accuracy below 50% for {consecutive_poor} consecutive days",
            "recent_accuracies": recent_accuracies[-10:],
        }
        _save_json(ML_WEIGHT_STATE, state)


def _verdict(buy_correct, buy_total, signal_useful, signal_checks) -> str:
    if buy_total == 0:
        return "Insufficient data"
    rate = buy_correct / buy_total * 100
    if rate >= 60:
        return "Model working well"
    elif rate >= 50:
        return "Model marginally useful"
    else:
        return "Model underperforming — needs investigation"


def format_validation_report(report: dict) -> str:
    """Format daily validation for Discord."""
    lines = []
    lines.append("🔍 **Daily Prediction Validation**")
    lines.append("")
    
    if report.get("error"):
        lines.append(f"⚠️ {report['error']}")
        return "\n".join(lines)
    
    spy_ret = report.get("spy_return")
    lines.append(f"📅 Validating predictions from: {report.get('prev_scan_timestamp', 'N/A')}")
    lines.append(f"📊 SPY today: {spy_ret:+.2f}%" if spy_ret is not None else "📊 SPY: N/A")
    lines.append("")
    
    # Signal group performance
    stats = report.get("signal_stats", {})
    for signal in ["STRONG_BUY", "BUY", "HOLD", "WAIT"]:
        if signal not in stats:
            continue
        s = stats[signal]
        emoji = "🟢" if signal in ("BUY", "STRONG_BUY") else "⚪"
        beat = f", beat SPY {s['beat_spy_rate']}%" if s.get("beat_spy_rate") is not None else ""
        lines.append(f"{emoji} **{signal}** ({s['count']}只): avg return {s['avg_return']:+.2f}%{beat}")
    
    lines.append("")
    
    # Key verdict
    useful = report.get("signal_useful")
    if useful is not None:
        if useful:
            lines.append("✅ BUY 信号今天跑赢了 HOLD — 信号有效")
        else:
            lines.append("❌ BUY 信号今天没跑赢 HOLD — 信号失效")
    
    corr = report.get("score_return_correlation")
    if corr is not None:
        corr_emoji = "✅" if corr > 0.1 else "⚠️" if corr > 0 else "❌"
        lines.append(f"{corr_emoji} 评分-收益相关性: {corr:.3f}")
    
    return "\n".join(lines)
