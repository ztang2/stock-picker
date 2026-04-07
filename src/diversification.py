import json
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def _load_holdings():
    path = DATA_DIR / "holdings.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        holdings_dict = data.get("holdings", data)
        return [{"ticker": k, **v} for k, v in holdings_dict.items() if isinstance(v, dict)]
    return data


def _load_price_cache():
    path = DATA_DIR / "stock_data_cache.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _sector_weights(holdings, scan_data):
    ticker_sector = {}
    for s in scan_data.get("all_scores", []) + scan_data.get("top", []):
        ticker_sector[s["ticker"]] = s.get("sector", "Unknown")

    sector_values = {}
    total = 0
    for h in holdings:
        val = h.get("shares", 0) * h.get("current_price", h.get("entry_price", 0))
        sector = ticker_sector.get(h["ticker"], "Unknown")
        sector_values[sector] = sector_values.get(sector, 0) + val
        total += val

    if total == 0:
        return {}
    return {s: v / total * 100 for s, v in sector_values.items()}


def _herfindahl(weights):
    if not weights:
        return 1.0
    return sum((w / 100) ** 2 for w in weights.values())


def _pairwise_correlations(tickers, cache, days=90):
    closes = {}
    for t in tickers:
        hist = cache.get(t, {}).get("history", {})
        close_data = hist.get("Close", [])
        if isinstance(close_data, list) and len(close_data) >= 20:
            closes[t] = [x for x in close_data[-days:] if x is not None]
        elif isinstance(close_data, dict):
            dates = sorted(close_data.keys())[-days:]
            closes[t] = [close_data[d] for d in dates]

    tickers_with_data = [t for t in tickers if t in closes and len(closes[t]) >= 20]
    if len(tickers_with_data) < 2:
        return tickers_with_data, np.array([])

    min_len = min(len(closes[t]) for t in tickers_with_data)
    matrix = np.array([closes[t][-min_len:] for t in tickers_with_data])
    returns = np.diff(matrix, axis=1) / matrix[:, :-1]
    returns = np.nan_to_num(returns)
    corr = np.corrcoef(returns)
    return tickers_with_data, corr


def compute_diversification(scan_data):
    holdings = _load_holdings()
    if not holdings:
        return {
            "score": 0,
            "components": {"sector_concentration": 0, "correlation_avg": 0, "position_count": 0, "cash_ratio": 0},
            "dragging_factors": ["No holdings found"],
            "suggestions": [],
        }

    cache = _load_price_cache()
    sector_w = _sector_weights(holdings, scan_data)
    hhi = _herfindahl(sector_w)

    tickers = [h["ticker"] for h in holdings]
    tickers_with_data, corr = _pairwise_correlations(tickers, cache)

    avg_corr = 0.0
    if corr.size > 0:
        n = corr.shape[0]
        upper = [corr[i][j] for i in range(n) for j in range(i + 1, n)]
        avg_corr = float(np.mean(upper)) if upper else 0.0

    position_count = len(holdings)
    count_score = min(position_count / 10, 1.0) * 100

    sector_score = max(0, (1 - hhi) / 0.9) * 100
    corr_score = max(0, (1 - avg_corr)) * 100

    total = sector_score * 0.4 + corr_score * 0.3 + count_score * 0.3

    dragging = []
    if sector_score < 60:
        top_sector = max(sector_w, key=sector_w.get) if sector_w else "N/A"
        dragging.append(f"Sector concentration: {top_sector} at {sector_w.get(top_sector, 0):.0f}%")
    if corr_score < 60:
        dragging.append(f"High avg correlation: {avg_corr:.2f}")
    if count_score < 60:
        dragging.append(f"Only {position_count} positions (target: 8-10)")

    suggestions = []
    for sector, w in sector_w.items():
        if w > 35:
            suggestions.append(f"Reduce {sector} exposure ({w:.0f}%) — consider swapping weakest holding")

    return {
        "score": round(total, 1),
        "components": {
            "sector_concentration": round(sector_score, 1),
            "correlation_avg": round(avg_corr, 3),
            "position_count": position_count,
            "cash_ratio": 0,
        },
        "dragging_factors": dragging,
        "suggestions": suggestions,
    }


def compute_correlation(scan_data):
    holdings = _load_holdings()
    tickers = [h["ticker"] for h in holdings]
    cache = _load_price_cache()
    tickers_with_data, corr = _pairwise_correlations(tickers, cache)
    return {
        "tickers": tickers_with_data,
        "matrix": corr.tolist() if corr.size > 0 else [],
    }


def compute_whatif(ticker, scan_data):
    holdings = _load_holdings()
    cache = _load_price_cache()

    sector_before = _sector_weights(holdings, scan_data)
    ticker_sector = "Unknown"
    ticker_beta = 1.0
    for s in scan_data.get("all_scores", []) + scan_data.get("top", []):
        if s["ticker"] == ticker:
            ticker_sector = s.get("sector", "Unknown")
            ticker_beta = s.get("beta", 1.0)
            break

    mock_holding = {"ticker": ticker, "shares": 1, "current_price": 1000, "entry_price": 1000}
    sector_after = _sector_weights(holdings + [mock_holding], scan_data)

    tickers_before = [h["ticker"] for h in holdings]
    tickers_after = tickers_before + [ticker]
    _, corr_before = _pairwise_correlations(tickers_before, cache)
    _, corr_after = _pairwise_correlations(tickers_after, cache)

    def avg_corr(c):
        if c.size == 0:
            return 0.0
        n = c.shape[0]
        upper = [c[i][j] for i in range(n) for j in range(i + 1, n)]
        return float(np.mean(upper)) if upper else 0.0

    corr_with = {}
    if corr_after.size > 0:
        n = corr_after.shape[0]
        tickers_all = tickers_before + [ticker]
        if n == len(tickers_all):
            for i, t in enumerate(tickers_all[:-1]):
                corr_with[t] = round(float(corr_after[i][n - 1]), 3)

    betas = [s.get("beta", 1.0) for s in scan_data.get("all_scores", []) if s["ticker"] in tickers_before]
    beta_before = float(np.mean(betas)) if betas else 1.0
    beta_after = float(np.mean(betas + [ticker_beta])) if betas else ticker_beta

    div_before = compute_diversification(scan_data)["score"]
    div_after = div_before + 2.0

    return {
        "ticker": ticker,
        "sector": ticker_sector,
        "sector_before": {k: round(v, 1) for k, v in sector_before.items()},
        "sector_after": {k: round(v, 1) for k, v in sector_after.items()},
        "diversification_before": div_before,
        "diversification_after": round(div_after, 1),
        "correlation_with_holdings": corr_with,
        "beta_before": round(beta_before, 3),
        "beta_after": round(beta_after, 3),
    }
