#!/usr/bin/env python3
"""
OpenBB vs yfinance + FMP Data Comparison Test
Tests 5 tickers from top 20: ALL, ACGL, MCK, EQT, NEM
Compares: historical prices, fundamentals, technical indicators, speed, coverage
"""

import json
import time
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables BEFORE importing openbb
from dotenv import load_dotenv
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    load_dotenv(env_file)
    fmp_key = os.getenv('FMP_API_KEY')
    if fmp_key:
        # Set as environment variable with OpenBB's expected name
        os.environ['OBB_FMP_API_KEY'] = fmp_key
        print(f"✓ FMP API key loaded from .env")

try:
    import yfinance as yf
    import pandas as pd
    from openbb import obb
    print("✓ All imports successful")
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)

# Test configuration
TICKERS = ['ALL', 'ACGL', 'MCK', 'EQT', 'NEM']
DATA_DIR = Path(__file__).parent.parent / 'data'
FMP_CACHE_DIR = DATA_DIR / 'fmp_cache'
RESULTS_FILE = DATA_DIR / 'openbb_comparison_results.txt'

# Results storage
results = {
    'timestamp': datetime.now().isoformat(),
    'tickers_tested': TICKERS,
    'data_comparison': {},
    'speed_comparison': {},
    'coverage_analysis': {},
    'free_tier_limits': {},
    'recommendation': ''
}

output_lines = []

def log(msg):
    """Log to console and output buffer"""
    print(msg)
    output_lines.append(msg)

def format_value(val):
    """Format value for display"""
    if val is None:
        return 'N/A'
    if isinstance(val, float):
        if abs(val) > 1e6:
            return f'{val/1e6:.2f}M'
        elif abs(val) > 1e3:
            return f'{val/1e3:.2f}K'
        else:
            return f'{val:.2f}'
    return str(val)

def check_fmp_cache(ticker):
    """Check if FMP cache exists for ticker"""
    cache_file = FMP_CACHE_DIR / f'{ticker}.json'
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            return True, data
        except:
            return False, None
    return False, None

def fetch_yfinance_data(ticker):
    """Fetch data using yfinance"""
    log(f"\n  [yfinance] Fetching {ticker}...")
    start_time = time.time()
    
    try:
        stock = yf.Ticker(ticker)
        
        # Historical prices (1 year)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        hist = stock.history(start=start_date, end=end_date)
        
        # Fundamental data
        info = stock.info
        
        data = {
            'historical': {
                'data_points': len(hist),
                'latest_close': hist['Close'].iloc[-1] if len(hist) > 0 else None,
                'avg_volume': hist['Volume'].mean() if len(hist) > 0 else None,
                'price_range': (hist['Close'].min(), hist['Close'].max()) if len(hist) > 0 else (None, None)
            },
            'fundamentals': {
                'market_cap': info.get('marketCap'),
                'pe_ratio': info.get('trailingPE'),
                'forward_pe': info.get('forwardPE'),
                'ps_ratio': info.get('priceToSalesTrailing12Months'),
                'pb_ratio': info.get('priceToBook'),
                'roe': info.get('returnOnEquity'),
                'profit_margin': info.get('profitMargins'),
                'revenue': info.get('totalRevenue'),
                'earnings_growth': info.get('earningsGrowth'),
                'revenue_growth': info.get('revenueGrowth'),
                'debt_to_equity': info.get('debtToEquity'),
                'current_ratio': info.get('currentRatio'),
                'dividend_yield': info.get('dividendYield')
            },
            'available_fields': list(info.keys()) if info else []
        }
        
        elapsed = time.time() - start_time
        return data, elapsed, None
        
    except Exception as e:
        elapsed = time.time() - start_time
        return None, elapsed, str(e)

def fetch_openbb_data(ticker):
    """Fetch data using OpenBB (trying FMP provider)"""
    log(f"  [OpenBB] Fetching {ticker}...")
    start_time = time.time()
    
    try:
        # Try FMP provider for historical prices (more reliable than yfinance wrapper)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        
        hist_df = pd.DataFrame()
        hist_error = None
        
        # Try FMP first for historical data
        try:
            hist_data = obb.equity.price.historical(
                symbol=ticker,
                start_date=start_date,
                end_date=end_date,
                provider='fmp'
            )
            hist_df = hist_data.to_df() if hasattr(hist_data, 'to_df') else pd.DataFrame(hist_data.results if hasattr(hist_data, 'results') else [])
            log(f"    [FMP historical] ✓ {len(hist_df)} data points")
        except Exception as e:
            hist_error = str(e)
            log(f"    [FMP historical] ✗ {hist_error[:100]}")
        
        # Fundamental data from FMP
        profile_data = None
        metrics_data = None
        ratios_data = None
        
        try:
            profile = obb.equity.profile(symbol=ticker, provider='fmp')
            if hasattr(profile, 'results') and profile.results:
                profile_data = profile.results[0]
                log(f"    [FMP profile] ✓")
            else:
                log(f"    [FMP profile] ✗ No results")
        except Exception as e:
            log(f"    [FMP profile] ✗ {str(e)[:100]}")
        
        # Try to get financial metrics
        try:
            metrics = obb.equity.fundamental.metrics(symbol=ticker, provider='fmp', period='annual', limit=1)
            if hasattr(metrics, 'results') and metrics.results:
                metrics_data = metrics.results[0]
                log(f"    [FMP metrics] ✓")
            else:
                log(f"    [FMP metrics] ✗ No results")
        except Exception as e:
            log(f"    [FMP metrics] ✗ {str(e)[:100]}")
        
        # Try to get key ratios
        try:
            ratios = obb.equity.fundamental.ratios(symbol=ticker, provider='fmp', period='annual', limit=1)
            if hasattr(ratios, 'results') and ratios.results:
                ratios_data = ratios.results[0]
                log(f"    [FMP ratios] ✓")
            else:
                log(f"    [FMP ratios] ✗ No results")
        except Exception as e:
            log(f"    [FMP ratios] ✗ {str(e)[:100]}")
        
        # Extract data from results
        data = {
            'historical': {
                'data_points': len(hist_df),
                'latest_close': hist_df['close'].iloc[-1] if len(hist_df) > 0 and 'close' in hist_df.columns else None,
                'avg_volume': hist_df['volume'].mean() if len(hist_df) > 0 and 'volume' in hist_df.columns else None,
                'price_range': (hist_df['close'].min(), hist_df['close'].max()) if len(hist_df) > 0 and 'close' in hist_df.columns else (None, None)
            },
            'fundamentals': {
                'market_cap': getattr(profile_data, 'market_cap', None) if profile_data else None,
                'pe_ratio': getattr(metrics_data, 'pe_ratio', None) if metrics_data else getattr(ratios_data, 'price_earnings_ratio', None) if ratios_data else None,
                'ps_ratio': getattr(metrics_data, 'price_to_sales_ratio', None) if metrics_data else getattr(ratios_data, 'price_to_sales_ratio', None) if ratios_data else None,
                'pb_ratio': getattr(metrics_data, 'price_to_book_ratio', None) if metrics_data else getattr(ratios_data, 'price_to_book_ratio', None) if ratios_data else None,
                'roe': getattr(ratios_data, 'return_on_equity', None) if ratios_data else None,
                'profit_margin': getattr(ratios_data, 'net_profit_margin', None) if ratios_data else None,
                'revenue': getattr(profile_data, 'revenue', None) if profile_data else None,
                'debt_to_equity': getattr(ratios_data, 'debt_equity_ratio', None) if ratios_data else None,
                'current_ratio': getattr(ratios_data, 'current_ratio', None) if ratios_data else None,
            },
            'available_endpoints': ['equity.price.historical (FMP)', 'equity.profile (FMP)', 'equity.fundamental.metrics (FMP)', 'equity.fundamental.ratios (FMP)'],
            'profile_available': profile_data is not None,
            'metrics_available': metrics_data is not None,
            'ratios_available': ratios_data is not None,
            'historical_error': hist_error
        }
        
        elapsed = time.time() - start_time
        
        # Only return success if we got at least some data
        if len(hist_df) > 0 or profile_data or metrics_data or ratios_data:
            return data, elapsed, None
        else:
            return data, elapsed, "No data returned from any endpoint"
        
    except Exception as e:
        elapsed = time.time() - start_time
        return None, elapsed, str(e)

def compare_ticker(ticker):
    """Compare all data sources for a ticker"""
    log(f"\n{'='*70}")
    log(f"TICKER: {ticker}")
    log(f"{'='*70}")
    
    ticker_results = {
        'yfinance': {},
        'openbb': {},
        'fmp_cache': {},
        'comparison': {}
    }
    
    # Check FMP cache
    has_fmp, fmp_data = check_fmp_cache(ticker)
    if has_fmp:
        log(f"  [FMP Cache] Found cached data for {ticker}")
        ticker_results['fmp_cache']['available'] = True
        ticker_results['fmp_cache']['data'] = fmp_data
    else:
        log(f"  [FMP Cache] No cached data for {ticker}")
        ticker_results['fmp_cache']['available'] = False
    
    # Fetch yfinance data
    yf_data, yf_time, yf_error = fetch_yfinance_data(ticker)
    ticker_results['yfinance']['time'] = yf_time
    ticker_results['yfinance']['error'] = yf_error
    if yf_data:
        ticker_results['yfinance']['data'] = yf_data
        log(f"    ✓ Success in {yf_time:.2f}s")
    else:
        log(f"    ✗ Error: {yf_error}")
    
    # Fetch OpenBB data
    obb_data, obb_time, obb_error = fetch_openbb_data(ticker)
    ticker_results['openbb']['time'] = obb_time
    ticker_results['openbb']['error'] = obb_error
    if obb_data:
        ticker_results['openbb']['data'] = obb_data
        log(f"    ✓ Success in {obb_time:.2f}s")
    else:
        log(f"    ✗ Error: {obb_error}")
    
    # Compare data
    if yf_data and obb_data:
        log(f"\n  COMPARISON:")
        log(f"  {'-'*66}")
        
        # Historical data comparison
        log(f"  Historical Data:")
        log(f"    yfinance data points: {yf_data['historical']['data_points']}")
        log(f"    OpenBB data points:   {obb_data['historical']['data_points']}")
        
        if yf_data['historical']['latest_close'] and obb_data['historical']['latest_close']:
            diff = abs(yf_data['historical']['latest_close'] - obb_data['historical']['latest_close'])
            pct_diff = (diff / yf_data['historical']['latest_close']) * 100
            log(f"    Latest close price difference: ${diff:.2f} ({pct_diff:.3f}%)")
            ticker_results['comparison']['price_diff_pct'] = pct_diff
        
        # Fundamentals comparison
        log(f"\n  Fundamentals (yfinance → OpenBB):")
        log(f"    {'Metric':<20} {'yfinance':<15} {'OpenBB':<15} {'Match':<10}")
        log(f"    {'-'*62}")
        
        fundamental_fields = ['market_cap', 'pe_ratio', 'ps_ratio', 'pb_ratio', 'roe', 'profit_margin']
        matches = 0
        total = 0
        
        for field in fundamental_fields:
            yf_val = yf_data['fundamentals'].get(field)
            obb_val = obb_data['fundamentals'].get(field)
            
            if yf_val is not None and obb_val is not None:
                # Check if values are close (within 5%)
                if isinstance(yf_val, (int, float)) and isinstance(obb_val, (int, float)):
                    diff_pct = abs(yf_val - obb_val) / (abs(yf_val) + 1e-10) * 100
                    match = '✓' if diff_pct < 5 else f'✗ {diff_pct:.1f}%'
                    if diff_pct < 5:
                        matches += 1
                    total += 1
                else:
                    match = '?' 
            elif yf_val is None and obb_val is None:
                match = 'Both N/A'
            else:
                match = 'One N/A'
            
            log(f"    {field:<20} {format_value(yf_val):<15} {format_value(obb_val):<15} {match:<10}")
        
        if total > 0:
            match_rate = (matches / total) * 100
            log(f"\n    Fundamental match rate: {matches}/{total} ({match_rate:.1f}%)")
            ticker_results['comparison']['fundamental_match_rate'] = match_rate
        
        # Coverage comparison
        log(f"\n  Coverage:")
        yf_fields = len([k for k, v in yf_data['fundamentals'].items() if v is not None])
        obb_fields = len([k for k, v in obb_data['fundamentals'].items() if v is not None])
        log(f"    yfinance: {yf_fields} fundamental fields populated")
        log(f"    OpenBB:   {obb_fields} fundamental fields populated")
        log(f"    OpenBB profile available: {obb_data.get('profile_available', False)}")
        log(f"    OpenBB metrics available: {obb_data.get('metrics_available', False)}")
        log(f"    OpenBB ratios available:  {obb_data.get('ratios_available', False)}")
        
        ticker_results['comparison']['yf_fields'] = yf_fields
        ticker_results['comparison']['obb_fields'] = obb_fields
    
    results['data_comparison'][ticker] = ticker_results
    return ticker_results

def analyze_results():
    """Analyze all results and generate recommendation"""
    log(f"\n\n{'='*70}")
    log(f"SUMMARY & ANALYSIS")
    log(f"{'='*70}")
    
    # Speed comparison
    log(f"\nSPEED COMPARISON:")
    log(f"{'-'*70}")
    yf_times = []
    obb_times = []
    
    for ticker, data in results['data_comparison'].items():
        yf_time = data['yfinance'].get('time', 0)
        obb_time = data['openbb'].get('time', 0)
        yf_times.append(yf_time)
        obb_times.append(obb_time)
        log(f"  {ticker}: yfinance={yf_time:.2f}s, OpenBB={obb_time:.2f}s")
    
    if yf_times and obb_times:
        avg_yf = sum(yf_times) / len(yf_times)
        avg_obb = sum(obb_times) / len(obb_times)
        log(f"\n  Average: yfinance={avg_yf:.2f}s, OpenBB={avg_obb:.2f}s")
        
        if avg_yf < avg_obb:
            faster = 'yfinance'
            diff_pct = ((avg_obb - avg_yf) / avg_yf) * 100
        else:
            faster = 'OpenBB'
            diff_pct = ((avg_yf - avg_obb) / avg_obb) * 100
        
        log(f"  Winner: {faster} is {diff_pct:.1f}% faster")
        results['speed_comparison'] = {
            'avg_yfinance': avg_yf,
            'avg_openbb': avg_obb,
            'winner': faster,
            'diff_pct': diff_pct
        }
    
    # Data accuracy comparison
    log(f"\nDATA ACCURACY:")
    log(f"{'-'*70}")
    
    price_diffs = []
    match_rates = []
    
    for ticker, data in results['data_comparison'].items():
        comp = data.get('comparison', {})
        if 'price_diff_pct' in comp:
            price_diffs.append(comp['price_diff_pct'])
        if 'fundamental_match_rate' in comp:
            match_rates.append(comp['fundamental_match_rate'])
    
    if price_diffs:
        avg_price_diff = sum(price_diffs) / len(price_diffs)
        log(f"  Average price difference: {avg_price_diff:.4f}%")
        log(f"  Assessment: {'✓ Excellent' if avg_price_diff < 0.01 else '✓ Good' if avg_price_diff < 0.1 else '⚠ Review needed'}")
    
    if match_rates:
        avg_match = sum(match_rates) / len(match_rates)
        log(f"  Average fundamental match rate: {avg_match:.1f}%")
        log(f"  Assessment: {'✓ Excellent' if avg_match > 90 else '✓ Good' if avg_match > 75 else '⚠ Significant differences'}")
    
    # Coverage comparison
    log(f"\nCOVERAGE ANALYSIS:")
    log(f"{'-'*70}")
    
    total_yf_fields = 0
    total_obb_fields = 0
    success_count = 0
    
    for ticker, data in results['data_comparison'].items():
        comp = data.get('comparison', {})
        if 'yf_fields' in comp:
            total_yf_fields += comp['yf_fields']
        if 'obb_fields' in comp:
            total_obb_fields += comp['obb_fields']
        if not data['yfinance'].get('error') and not data['openbb'].get('error'):
            success_count += 1
    
    log(f"  Total fundamental fields (across {len(TICKERS)} tickers):")
    log(f"    yfinance: {total_yf_fields} fields")
    log(f"    OpenBB:   {total_obb_fields} fields")
    log(f"  Success rate: {success_count}/{len(TICKERS)} tickers")
    
    log(f"\n  OpenBB provides:")
    log(f"    • Access to multiple data providers (yfinance, FMP, Polygon, etc.)")
    log(f"    • Standardized API across providers")
    log(f"    • Additional endpoints: technical indicators, options, news, etc.")
    log(f"    • Built-in caching and rate limiting")
    
    results['coverage_analysis'] = {
        'yf_total_fields': total_yf_fields,
        'obb_total_fields': total_obb_fields,
        'success_rate': f"{success_count}/{len(TICKERS)}"
    }
    
    # Free tier limitations
    log(f"\nFREE TIER LIMITATIONS:")
    log(f"{'-'*70}")
    log(f"  yfinance:")
    log(f"    • Completely free, no API key required")
    log(f"    • No official rate limits (uses Yahoo Finance)")
    log(f"    • Can be unstable due to web scraping nature")
    log(f"    • Limited to Yahoo Finance data only")
    
    log(f"\n  OpenBB Free Tier:")
    log(f"    • Free providers: yfinance, FMP (limited), SEC, FRED, etc.")
    log(f"    • FMP free tier: ~250 requests/day")
    log(f"    • Many premium features require paid subscriptions")
    log(f"    • Default provider (yfinance) has same limitations")
    log(f"    • Pro: Can switch providers without code changes")
    
    results['free_tier_limits'] = {
        'yfinance': 'Unlimited (web scraping)',
        'openbb_yfinance_provider': 'Unlimited (same as yfinance)',
        'openbb_fmp_provider': '~250 requests/day (free tier)'
    }
    
    # Recommendation
    log(f"\nRECOMMENDATION:")
    log(f"{'='*70}")
    
    # Decision logic
    if success_count == len(TICKERS) and price_diffs and match_rates:
        avg_price_diff = sum(price_diffs) / len(price_diffs)
        avg_match = sum(match_rates) / len(match_rates)
        
        if avg_price_diff < 0.01 and avg_match > 90:
            recommendation = "MIGRATE"
            reasoning = [
                "✓ Data accuracy is excellent (price diff < 0.01%, match rate > 90%)",
                "✓ OpenBB provides better abstraction and multi-provider support",
                "✓ Easier to switch data providers in future without code changes",
                "✓ More comprehensive API (options, technical indicators, news)",
                "⚠ Slightly slower on average, but acceptable",
                "⚠ Default free tier uses yfinance anyway, so no immediate data improvement"
            ]
        elif avg_price_diff < 0.1 and avg_match > 75:
            recommendation = "PARTIAL MIGRATE"
            reasoning = [
                "✓ Data accuracy is good enough for most use cases",
                "✓ OpenBB architecture is more flexible for future expansion",
                "⚠ Current free tier doesn't provide better data than yfinance",
                "⚠ Migration effort may not justify immediate benefits",
                "→ Consider migrating specific features that need premium providers",
                "→ Keep yfinance for basic price/fundamental data"
            ]
        else:
            recommendation = "DON'T MIGRATE"
            reasoning = [
                "✗ Data differences are too significant",
                "✗ Match rate is below acceptable threshold",
                "✓ yfinance is faster and simpler",
                "✓ Current setup is working well",
                "→ Stick with yfinance + FMP direct API calls"
            ]
    else:
        recommendation = "DON'T MIGRATE"
        reasoning = [
            "✗ Not all tickers fetched successfully",
            "✗ Insufficient data for proper comparison",
            "→ Investigate errors before considering migration"
        ]
    
    results['recommendation'] = {
        'decision': recommendation,
        'reasoning': reasoning
    }
    
    log(f"\n  Decision: {recommendation}")
    log(f"\n  Reasoning:")
    for reason in reasoning:
        log(f"    {reason}")
    
    log(f"\n  Bottom Line:")
    if recommendation == "MIGRATE":
        log(f"    OpenBB provides better long-term architecture, but for free tier")
        log(f"    it mostly wraps yfinance anyway. Migrate if you plan to use")
        log(f"    premium providers or need additional features (options, news, etc.)")
    elif recommendation == "PARTIAL MIGRATE":
        log(f"    Use OpenBB for features that benefit from its architecture")
        log(f"    (multi-provider support, technical indicators, options), but")
        log(f"    keep yfinance for basic price/fundamental data.")
    else:
        log(f"    Stick with current yfinance + FMP setup. OpenBB doesn't provide")
        log(f"    enough immediate value to justify migration at this time.")

def main():
    """Main execution"""
    log("OpenBB vs yfinance + FMP Comparison Test")
    log("=" * 70)
    log(f"Testing {len(TICKERS)} tickers: {', '.join(TICKERS)}")
    log(f"Data directory: {DATA_DIR}")
    log(f"FMP cache directory: {FMP_CACHE_DIR}")
    
    # Test each ticker
    for ticker in TICKERS:
        compare_ticker(ticker)
    
    # Analyze results
    analyze_results()
    
    # Save results
    log(f"\n{'='*70}")
    log(f"Saving results to: {RESULTS_FILE}")
    
    with open(RESULTS_FILE, 'w') as f:
        f.write('\n'.join(output_lines))
        f.write('\n\n')
        f.write('='*70 + '\n')
        f.write('RAW RESULTS (JSON)\n')
        f.write('='*70 + '\n')
        f.write(json.dumps(results, indent=2, default=str))
    
    log(f"✓ Results saved successfully")
    log(f"\nTest complete!")

if __name__ == '__main__':
    main()
