# Stock Picker

US stock screening system using S&P 500 + S&P 400 MidCap universe (903 stocks) with multi-stage scoring pipeline and React dashboard.

## Setup

```bash
cd stock-picker
pip install -r requirements.txt

# Frontend (optional — for development)
cd frontend
npm install
```

## Usage

### API Server
```bash
uvicorn src.api:app --reload --port 8000
# Dashboard at http://localhost:8000
```

### Frontend Dev Mode
```bash
cd frontend
npm run dev
# Dev server at http://localhost:5173 (proxies API to :8000)
```

### Frontend Production Build
```bash
cd frontend
npm run build   # outputs to static/dist/
```

### CLI
```bash
python -m src.pipeline
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /scan` | Run full scan (supports filters, see below) |
| `GET /scan/cached` | Return last results |
| `GET /stock/{ticker}` | Detailed breakdown for one stock |
| `GET /sectors` | List all sectors with stock counts |
| `GET /top/{sector}` | Top stocks in a specific sector |

### Filtered Scans

```
GET /scan?sector=Technology&min_cap=10e9&max_cap=500e9&exclude=TSLA,META
```

Query parameters:
- `sector` — Filter by sector (e.g. Technology, Healthcare)
- `min_cap` — Minimum market cap
- `max_cap` — Maximum market cap
- `exclude` — Comma-separated tickers to exclude

## Scoring

Each stock scored 0-100 via percentile ranking across 4 categories:

- **Fundamentals (35%)**: Revenue growth, profit margin, ROE, debt-to-equity, FCF yield, FCF/net income ratio, earnings growth
- **Valuation (25%)**: P/E, P/S, PEG ratio
- **Technicals (25%)**: RSI, MACD, price vs 50/200 MA, volume trend
- **Risk (15%)**: Beta (vs SPY), max drawdown, Sharpe ratio, volatility

### Sector-Relative Scoring

Stocks are also ranked relative to their sector peers on P/E, P/S, revenue growth, and ROE. Sector-relative ranks are included in scan results.

## Configuration

See `config.yaml` for weights, thresholds, and filtering options.

### Filtering Options (config.yaml)

```yaml
filters:
  sectors: ["Technology"]     # Only these sectors
  industries: []              # Only these industries
  min_market_cap: 10.0e9      # Override minimum
  max_market_cap: 500.0e9     # Maximum cap
  exclude_tickers: ["TSLA"]   # Skip these
```
