#!/usr/bin/env python3
"""Test script for position sizing module."""

import json
from src.position_sizing import (
    get_single_ticker_sizing,
    get_portfolio_sizing,
    get_rebalance_suggestions
)


def test_single_ticker():
    """Test conviction score and sizing for a single ticker."""
    print("\n" + "="*60)
    print("TEST 1: Single Ticker Sizing (INCY)")
    print("="*60)
    
    result = get_single_ticker_sizing(
        ticker="INCY",
        total_portfolio_value=50000,
        num_positions=10
    )
    
    print(json.dumps(result, indent=2))
    print(f"\n✅ INCY conviction: {result['conviction']['conviction_score']:.2f}/100")
    print(f"✅ Recommended allocation: {result['sizing']['final_allocation_pct']:.2f}% (${result['sizing']['dollar_amount']:,.0f})")


def test_portfolio_sizing():
    """Test full portfolio sizing."""
    print("\n" + "="*60)
    print("TEST 2: Full Portfolio Sizing")
    print("="*60)
    
    result = get_portfolio_sizing(total_portfolio_value=10000)
    
    print(f"\nPortfolio: ${result['total_portfolio_value']:,.0f}")
    print(f"Positions: {result['num_positions']}")
    print(f"Total Allocated: {result['total_allocated_pct']:.2f}%")
    print("\nTop Conviction Positions:")
    
    for i, pos in enumerate(result['positions'][:5], 1):
        ticker = pos['ticker']
        conviction = pos['conviction']['conviction_score']
        pct = pos['sizing']['final_allocation_pct']
        dollars = pos['sizing']['dollar_amount']
        print(f"  {i}. {ticker:5} — {conviction:5.2f}/100 conviction → {pct:5.2f}% (${dollars:,.0f})")


def test_rebalance_suggestions():
    """Test rebalance suggestions for current holdings."""
    print("\n" + "="*60)
    print("TEST 3: Rebalance Suggestions")
    print("="*60)
    
    result = get_rebalance_suggestions(total_portfolio_value=10000)
    
    print(f"\nCurrent Portfolio Value: ${result['portfolio_value']:,.2f}")
    print(f"Positions: {result['num_positions']}\n")
    print("Rebalance Recommendations (sorted by urgency):")
    print("-" * 100)
    print(f"{'Ticker':<8} {'Current %':<12} {'Target %':<12} {'Diff %':<12} {'Action':<20} {'Days Held':<12}")
    print("-" * 100)
    
    for sug in result['rebalance_suggestions'][:10]:
        ticker = sug['ticker']
        current = sug['current_allocation_pct']
        target = sug['recommended_allocation_pct']
        diff = sug['diff_pct']
        action = sug['action']
        days = sug.get('days_held', 'N/A')
        
        # Color code based on action
        if 'DECREASE' in action:
            symbol = '🔻'
        elif 'INCREASE' in action:
            symbol = '🔺'
        else:
            symbol = '⏸️ '
        
        print(f"{ticker:<8} {current:>10.2f}%  {target:>10.2f}%  {diff:>+10.2f}%  {symbol} {action:<18} {days}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("POSITION SIZING MODULE TEST SUITE")
    print("Testing conviction-based allocation and rebalance suggestions")
    print("="*60)
    
    test_single_ticker()
    test_portfolio_sizing()
    test_rebalance_suggestions()
    
    print("\n" + "="*60)
    print("✅ All tests completed successfully!")
    print("="*60)
    print("\nAPI Endpoints:")
    print("  GET /sizing/{ticker}?portfolio_value=50000&num_positions=10")
    print("  GET /sizing/portfolio?portfolio_value=10000")
    print("  GET /sizing/portfolio?portfolio_value=10000&rebalance=true")
    print()
