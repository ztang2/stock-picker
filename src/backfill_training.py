"""
Backfill ML training data using 5 years of historical OHLCV data.
Computes Alpha158 features for all stocks, then calculates forward returns.

Usage:
    python -m src.backfill_training [--years 5] [--workers 10]
"""

import json
import time
import logging
import argparse
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from .alpha158 import compute_alpha158_fast
from .universe import get_universe_tickers as get_universe

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

DATA_DIR = Path(__file__).parent.parent / "data"
FORWARD_DAYS = 20  # trading days forward return


def download_history(tickers: List[str], years: int = 5) -> Dict[str, pd.DataFrame]:
    """Download historical OHLCV for all tickers in batches."""
    end = datetime.now()
    start = end - timedelta(days=years * 365)
    
    logger.info(f"Downloading {len(tickers)} tickers, {start.date()} to {end.date()}")
    
    all_data = {}
    batch_size = 50
    
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            data = yf.download(
                batch, start=start.strftime('%Y-%m-%d'), 
                end=end.strftime('%Y-%m-%d'),
                progress=False, threads=True
            )
            
            if isinstance(data.columns, pd.MultiIndex):
                # yfinance returns ('Close','AAPL') format
                # Use xs to extract per-ticker DataFrames
                available_tickers = data.columns.get_level_values(1).unique()
                for t in batch:
                    try:
                        if t in available_tickers:
                            df = data.xs(t, level=1, axis=1).dropna(how='all')
                            if not df.empty and len(df) >= 60:
                                all_data[t] = df
                    except Exception:
                        pass
            else:
                # Single ticker without MultiIndex
                if not data.empty and len(data) >= 60:
                    all_data[batch[0]] = data.dropna(how='all')
            
            logger.info(f"  Batch {i//batch_size + 1}/{(len(tickers) + batch_size - 1)//batch_size}: "
                       f"got {len(all_data)} tickers total")
            
            # Rate limit
            if i + batch_size < len(tickers):
                time.sleep(1)
                
        except Exception as e:
            logger.warning(f"  Batch download failed: {e}")
            time.sleep(2)
    
    # Download SPY separately
    try:
        spy = yf.download('SPY', start=start.strftime('%Y-%m-%d'),
                          end=end.strftime('%Y-%m-%d'), progress=False)
        if isinstance(spy.columns, pd.MultiIndex):
            # yfinance returns ('Close','SPY') format — take first level
            spy.columns = spy.columns.get_level_values(0)
        all_data['SPY'] = spy
        logger.info(f"SPY: {len(spy)} rows, columns: {list(spy.columns)}")
    except Exception as e:
        logger.error(f"Failed to download SPY: {e}")
    
    logger.info(f"Downloaded {len(all_data)} tickers successfully")
    return all_data


def compute_forward_returns(close_prices: pd.Series, spy_close: pd.Series, 
                           days: int = FORWARD_DAYS) -> pd.DataFrame:
    """Compute forward return and excess return vs SPY."""
    # Align dates
    aligned = pd.DataFrame({'stock': close_prices, 'spy': spy_close}).dropna()
    
    stock_fwd = aligned['stock'].shift(-days) / aligned['stock'] - 1
    spy_fwd = aligned['spy'].shift(-days) / aligned['spy'] - 1
    
    result = pd.DataFrame({
        'forward_return': stock_fwd,
        'spy_return': spy_fwd,
        'excess_return': stock_fwd - spy_fwd,
        'beat_spy': (stock_fwd > spy_fwd).astype(int)
    }, index=aligned.index)
    
    return result


def build_training_dataset(all_data: Dict[str, pd.DataFrame], 
                           sample_every_n_days: int = 5) -> pd.DataFrame:
    """Build full training dataset with Alpha158 features and forward returns."""
    spy_data = all_data.get('SPY')
    if spy_data is None:
        raise ValueError("SPY data required")
    
    spy_close = spy_data['Close']
    if isinstance(spy_close, pd.DataFrame):
        spy_close = spy_close.iloc[:, 0]
    
    tickers = [t for t in all_data if t != 'SPY']
    logger.info(f"Computing features for {len(tickers)} tickers...")
    
    all_rows = []
    processed = 0
    
    for ticker in tickers:
        try:
            hist = all_data[ticker]
            if len(hist) < 120:  # Need 60 for features + some for forward returns
                continue
            
            # Compute Alpha158 features
            features = compute_alpha158_fast(hist)
            
            # Compute forward returns
            close = hist['Close']
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            returns = compute_forward_returns(close, spy_close)
            
            # Merge features and returns
            combined = features.join(returns, how='inner').dropna()
            
            # Sample every N days to reduce dataset size while keeping diversity
            if sample_every_n_days > 1:
                combined = combined.iloc[::sample_every_n_days]
            
            if len(combined) > 0:
                combined['ticker'] = ticker
                combined['date'] = combined.index
                all_rows.append(combined)
            
            processed += 1
            if processed % 100 == 0:
                logger.info(f"  Processed {processed}/{len(tickers)} tickers, "
                           f"{sum(len(r) for r in all_rows)} samples so far")
                
        except Exception as e:
            logger.warning(f"  Failed {ticker}: {e}")
    
    if not all_rows:
        return pd.DataFrame()
    
    dataset = pd.concat(all_rows, ignore_index=True)
    logger.info(f"Built dataset: {len(dataset)} samples, {len(dataset.columns)} columns, "
                f"{processed} tickers")
    
    return dataset


def save_dataset(dataset: pd.DataFrame, output_path: Path = None):
    """Save training dataset to parquet and JSON summary."""
    if output_path is None:
        output_path = DATA_DIR / "alpha158_training.parquet"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save as parquet (efficient for large datasets)
    dataset.to_parquet(output_path, index=False)
    
    # Save summary
    feature_cols = [c for c in dataset.columns 
                    if c not in ['ticker', 'date', 'forward_return', 'spy_return', 
                                'excess_return', 'beat_spy']]
    
    summary = {
        'created_at': datetime.now().isoformat(),
        'total_samples': len(dataset),
        'tickers': dataset['ticker'].nunique(),
        'date_range': [str(dataset['date'].min()), str(dataset['date'].max())],
        'features': len(feature_cols),
        'feature_names': feature_cols,
        'beat_spy_rate': float(dataset['beat_spy'].mean()),
        'avg_excess_return': float(dataset['excess_return'].mean()),
        'forward_days': FORWARD_DAYS,
        'sample_frequency': 'every 5 trading days',
    }
    
    summary_path = output_path.parent / "alpha158_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    
    logger.info(f"Saved dataset to {output_path} ({output_path.stat().st_size / 1e6:.1f} MB)")
    logger.info(f"Summary: {json.dumps(summary, indent=2, default=str)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--years', type=int, default=5, help='Years of history')
    parser.add_argument('--sample-days', type=int, default=5, help='Sample every N days')
    args = parser.parse_args()
    
    # Get universe
    tickers = get_universe()
    logger.info(f"Universe: {len(tickers)} tickers")
    
    # Download
    all_data = download_history(tickers + ['SPY'], years=args.years)
    
    # Build dataset
    dataset = build_training_dataset(all_data, sample_every_n_days=args.sample_days)
    
    if dataset.empty:
        logger.error("No training data generated!")
        return
    
    # Save
    save_dataset(dataset)
    
    logger.info("Done!")


if __name__ == '__main__':
    main()
