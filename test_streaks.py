#!/usr/bin/env python3
"""Test script for streak tracking feature."""

import json
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

from src.pipeline import run_scan, RESULTS_FILE
from src.streak_tracker import get_all_streaks, update_streaks
from src.alerts import generate_morning_briefing

def main():
    print("\n" + "=" * 70)
    print("TESTING STREAK TRACKING FEATURE")
    print("=" * 70)
    
    # Step 1: Run a scan (this should automatically update streaks now)
    print("\n[1/5] Running scan...")
    result = run_scan(strategy="balanced")
    print(f"✅ Scan complete. {len(result.get('top', []))} stocks ranked.")
    
    # Step 2: Check if streaks were updated
    print("\n[2/5] Checking streaks...")
    streaks = get_all_streaks()
    print(f"✅ {len(streaks)} tickers have streak data")
    
    # Show top 5 by consecutive days
    sorted_streaks = sorted(streaks.items(), key=lambda x: x[1].get("consecutive_days", 0), reverse=True)
    print("\nTop 5 by consecutive days:")
    for ticker, data in sorted_streaks[:5]:
        days = data.get("consecutive_days", 0)
        first = data.get("first_seen", "N/A")
        last = data.get("last_seen", "N/A")
        print(f"  {ticker}: {days} days (first: {first}, last: {last})")
    
    # Step 3: Verify results have consecutive_days field
    print("\n[3/5] Verifying scan results have consecutive_days...")
    top_stocks = result.get("top", [])[:5]
    has_streak = all("consecutive_days" in stock for stock in top_stocks)
    if has_streak:
        print("✅ All top stocks have consecutive_days field")
        print("\nTop 5 stocks with streaks:")
        for stock in top_stocks:
            ticker = stock.get("ticker")
            days = stock.get("consecutive_days", 0)
            score = stock.get("composite_score", 0)
            print(f"  #{stock['rank']} {ticker}: {days} days (score: {score:.2f})")
    else:
        print("❌ ERROR: Some stocks missing consecutive_days field!")
        return
    
    # Step 4: Generate morning briefing
    print("\n[4/5] Generating morning briefing...")
    briefing = generate_morning_briefing()
    print("✅ Briefing generated")
    print("\n" + briefing)
    
    # Step 5: Check streak_tracker.json file
    print("\n[5/5] Checking streak_tracker.json...")
    streak_file = Path(__file__).parent / "data" / "streak_tracker.json"
    if streak_file.exists():
        print(f"✅ streak_tracker.json exists ({streak_file.stat().st_size} bytes)")
        with open(streak_file) as f:
            data = json.load(f)
            print(f"   Contains {len(data)} tickers")
    else:
        print("❌ ERROR: streak_tracker.json not found!")
        return
    
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)

if __name__ == "__main__":
    main()
