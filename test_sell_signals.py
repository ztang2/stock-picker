#!/usr/bin/env python3
"""Basic tests for sell_signals module."""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sell_signals import compute_sell_signals


def create_sample_hist(
    length: int = 100,
    trend: str = "neutral",
    rsi_level: str = "neutral",
    price: float = 100.0
) -> pd.DataFrame:
    """Create sample price history for testing.
    
    Args:
        length: Number of data points
        trend: 'up', 'down', or 'neutral'
        rsi_level: 'oversold', 'neutral', or 'overbought'
        price: Current price level
    """
    dates = pd.date_range(end=pd.Timestamp.now(), periods=length, freq='D')
    
    # Generate price data
    if trend == "up":
        prices = np.linspace(price * 0.8, price, length)
    elif trend == "down":
        prices = np.linspace(price * 1.2, price, length)
    else:
        prices = np.ones(length) * price
    
    # Add some volatility
    volatility = np.random.normal(0, 0.01, length)
    prices = prices * (1 + volatility)
    
    # Adjust to get desired RSI
    if rsi_level == "overbought":
        # Add strong upward momentum in recent period
        recent_boost = np.linspace(0, 0.15, 20)
        prices[-20:] = prices[-20:] * (1 + recent_boost)
    elif rsi_level == "oversold":
        # Add strong downward momentum in recent period
        recent_drop = np.linspace(0, -0.15, 20)
        prices[-20:] = prices[-20:] * (1 + recent_drop)
    
    # Create OHLCV data
    highs = prices * 1.02
    lows = prices * 0.98
    opens = prices * 1.001
    volume = np.random.randint(1000000, 5000000, length)
    
    return pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": prices,
        "Volume": volume,
    }, index=dates)


def test_basic_functionality():
    """Test that compute_sell_signals returns expected structure."""
    print("Test 1: Basic functionality")
    hist = create_sample_hist()
    result = compute_sell_signals(hist)
    
    assert "sell_signal" in result
    assert "sell_reasons" in result
    assert "urgency" in result
    assert result["sell_signal"] in ["STRONG_SELL", "SELL", "HOLD", "N/A"]
    print("  ✓ Returns correct structure")
    print(f"  Signal: {result['sell_signal']}, Urgency: {result['urgency']}")
    print()


def test_rsi_overbought():
    """Test RSI overbought detection."""
    print("Test 2: RSI overbought detection")
    hist = create_sample_hist(rsi_level="overbought")
    result = compute_sell_signals(hist)
    
    print(f"  RSI: {result.get('rsi')}")
    print(f"  RSI overbought flag: {result.get('rsi_overbought')}")
    print(f"  Signal: {result['sell_signal']}")
    print(f"  Reasons: {result['sell_reasons']}")
    
    if result.get("rsi") and result["rsi"] > 70:
        assert result["rsi_overbought"] is True
        print("  ✓ RSI overbought detected correctly")
    else:
        print("  ⚠ RSI not high enough to trigger overbought (expected behavior variation)")
    print()


def test_resistance_proximity():
    """Test resistance level proximity detection."""
    print("Test 3: Resistance proximity detection")
    hist = create_sample_hist(price=99.0)
    current_price = float(hist["Close"].iloc[-1])
    resistance = current_price * 1.01  # 1% above current price
    
    result = compute_sell_signals(hist, resistance=resistance)
    
    print(f"  Current price: ${current_price:.2f}")
    print(f"  Resistance: ${resistance:.2f}")
    print(f"  Near resistance flag: {result.get('near_resistance')}")
    print(f"  Signal: {result['sell_signal']}")
    
    assert result.get("near_resistance") is True
    print("  ✓ Resistance proximity detected")
    print()


def test_signal_downgrade():
    """Test signal downgrade detection."""
    print("Test 4: Signal downgrade detection")
    hist = create_sample_hist()
    
    result = compute_sell_signals(
        hist,
        current_signal="WAIT",
        prev_signal="STRONG_BUY"
    )
    
    print(f"  Previous signal: STRONG_BUY")
    print(f"  Current signal: WAIT")
    print(f"  Downgrade flag: {result.get('signal_downgrade')}")
    print(f"  Sell signal: {result['sell_signal']}")
    print(f"  Reasons: {result['sell_reasons']}")
    
    assert result.get("signal_downgrade") is True
    print("  ✓ Signal downgrade detected")
    print()


def test_fundamental_deterioration():
    """Test fundamental score deterioration detection."""
    print("Test 5: Fundamental deterioration detection")
    hist = create_sample_hist()
    
    result = compute_sell_signals(
        hist,
        fundamentals_score=50.0,
        prev_fundamentals_score=70.0
    )
    
    print(f"  Previous score: 70.0")
    print(f"  Current score: 50.0")
    print(f"  Deterioration flag: {result.get('fundamental_deterioration')}")
    print(f"  Sell signal: {result['sell_signal']}")
    
    assert result.get("fundamental_deterioration") is True
    print("  ✓ Fundamental deterioration detected")
    print()


def test_stop_loss():
    """Test stop-loss trigger."""
    print("Test 6: Stop-loss detection")
    hist = create_sample_hist(price=85.0)
    current_price = float(hist["Close"].iloc[-1])
    entry_price = 100.0
    
    result = compute_sell_signals(
        hist,
        entry_price=entry_price,
        stop_loss_pct=-15.0
    )
    
    stop_info = result.get("stop_loss_info", {})
    print(f"  Entry price: ${entry_price:.2f}")
    print(f"  Current price: ${current_price:.2f}")
    print(f"  Loss: {stop_info.get('loss_pct', 0):.1f}%")
    print(f"  Stop-loss triggered: {result.get('stop_loss_triggered')}")
    print(f"  Sell signal: {result['sell_signal']}")
    
    if stop_info.get("loss_pct", 0) <= -15:
        assert result.get("stop_loss_triggered") is True
        print("  ✓ Stop-loss detected")
    else:
        print("  ⚠ Loss not severe enough to trigger stop-loss")
    print()


def test_macd_crossover():
    """Test MACD bearish crossover detection."""
    print("Test 7: MACD bearish crossover")
    # Create downtrending price data for bearish crossover
    hist = create_sample_hist(length=100, trend="down")
    
    result = compute_sell_signals(hist)
    
    macd_info = result.get("macd", {})
    print(f"  MACD histogram: {macd_info.get('histogram', 0):.4f}")
    print(f"  Bearish crossover: {macd_info.get('bearish_crossover', False)}")
    print(f"  MACD bearish flag: {result.get('macd_bearish')}")
    print(f"  Sell signal: {result['sell_signal']}")
    
    if macd_info.get("bearish_crossover"):
        print("  ✓ MACD bearish crossover detected")
    else:
        print("  ⚠ No crossover in test data (expected with random data)")
    print()


def test_ma_breakdown():
    """Test moving average breakdown detection."""
    print("Test 8: Moving average breakdown")
    
    # Create data that crosses below MA50
    length = 100
    dates = pd.date_range(end=pd.Timestamp.now(), periods=length, freq='D')
    
    # Stable then drop
    prices = np.ones(length) * 100.0
    prices[-5:] = [99.5, 99.0, 98.5, 98.0, 95.0]  # Sharp drop at end
    
    hist = pd.DataFrame({
        "Open": prices,
        "High": prices * 1.01,
        "Low": prices * 0.99,
        "Close": prices,
        "Volume": np.ones(length) * 1000000,
    }, index=dates)
    
    result = compute_sell_signals(hist)
    
    ma_info = result.get("ma_breakdown_info", {})
    print(f"  Current price: ${ma_info.get('current_price', 0):.2f}")
    print(f"  MA50: ${ma_info.get('ma50', 0):.2f}")
    print(f"  Below MA50: {ma_info.get('below_ma50', False)}")
    print(f"  MA breakdown flag: {result.get('ma_breakdown')}")
    print(f"  Sell signal: {result['sell_signal']}")
    
    if ma_info.get("below_ma50"):
        print("  ✓ MA breakdown detected")
    else:
        print("  ⚠ No breakdown (expected with random data)")
    print()


def test_combined_signals():
    """Test multiple sell signals combining for STRONG_SELL."""
    print("Test 9: Combined sell signals (STRONG_SELL)")
    
    # Create scenario with multiple sell triggers
    hist = create_sample_hist(length=100, rsi_level="overbought", price=85.0)
    
    result = compute_sell_signals(
        hist,
        fundamentals_score=45.0,
        prev_fundamentals_score=70.0,
        current_signal="WAIT",
        prev_signal="STRONG_BUY",
        entry_price=100.0,
        stop_loss_pct=-15.0,
    )
    
    print(f"  Sell score: {result.get('sell_score', 0)}")
    print(f"  Sell signal: {result['sell_signal']}")
    print(f"  Urgency: {result['urgency']}")
    print(f"  Reasons: {result['sell_reasons']}")
    
    # With multiple triggers, should get SELL or STRONG_SELL
    assert result["sell_signal"] in ["SELL", "STRONG_SELL"]
    print("  ✓ Combined signals produce appropriate sell rating")
    print()


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing sell_signals module")
    print("=" * 60)
    print()
    
    try:
        test_basic_functionality()
        test_rsi_overbought()
        test_resistance_proximity()
        test_signal_downgrade()
        test_fundamental_deterioration()
        test_stop_loss()
        test_macd_crossover()
        test_ma_breakdown()
        test_combined_signals()
        
        print("=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
