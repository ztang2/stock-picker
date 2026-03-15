#!/usr/bin/env python3
"""Test the profit-taking module."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from profit_taker import check_profit_status, get_profit_summary

# Load holdings
holdings_file = Path(__file__).parent / "data" / "holdings.json"
holdings_data = json.loads(holdings_file.read_text())
holdings = holdings_data.get("holdings", {})

print("=" * 80)
print("PROFIT-TAKING STATUS CHECK")
print("=" * 80)
print()

# Run profit check
alerts = check_profit_status(holdings)

# Print summary
summary = get_profit_summary(alerts)
print("📊 SUMMARY:")
print(f"  Total positions: {summary['total_positions']}")
print(f"  Average gain: {summary['avg_gain_pct']:+.2f}%")
print(f"  🎯 TAKE PROFIT: {summary['take_profit_count']} ({', '.join(summary['take_profit_tickers']) if summary['take_profit_tickers'] else 'none'})")
print(f"  🟡 APPROACHING: {summary['approaching_count']} ({', '.join(summary['approaching_tickers']) if summary['approaching_tickers'] else 'none'})")
print(f"  ✅ COMPLETED: {summary['completed_count']}")
print()

# Print detailed alerts
print("=" * 80)
print("DETAILED ALERTS (sorted by urgency):")
print("=" * 80)
print()

for alert in alerts:
    print(f"{'='*60}")
    print(f"Ticker: {alert['ticker']}")
    print(f"Status: {alert['status']}")
    print(f"Entry: ${alert['entry_price']:.2f} → Current: ${alert['current_price']:.2f}")
    print(f"Gain: {alert['gain_pct']:+.2f}%")
    if alert.get('beta'):
        print(f"Beta: {alert['beta']:.2f}")
    print(f"Tier Targets: {alert['tier_thresholds']}")
    print(f"Tiers Triggered: {alert['tiers_triggered']}")
    if alert.get('next_tier'):
        print(f"Next Tier: {alert['next_tier']} at {alert['next_tier_pct']:+.0f}%")
        if alert.get('distance_to_next_pct'):
            print(f"Distance: {alert['distance_to_next_pct']:.2f}%")
    if alert.get('days_held'):
        print(f"Days Held: {alert['days_held']}")
    print()
    print(f"MESSAGE: {alert['message']}")
    print()

print("=" * 80)
print("Test complete!")
print(f"State saved to: data/profit_targets.json")
print("=" * 80)
