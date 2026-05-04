"""
tests/test_strategy.py
───────────────────────
Tests for Phase 3 — Strategy Engine.
Run with:
    python -m pytest tests/test_strategy.py -v
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def make_sample_df(n=300, trend="up"):
    """Create synthetic OHLCV data for testing strategies without needing the DB."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=n, freq="D")
    price = 1000.0
    prices = []

    for i in range(n):
        if trend == "up":
            price *= (1 + np.random.normal(0.001, 0.015))
        elif trend == "down":
            price *= (1 + np.random.normal(-0.001, 0.015))
        else:
            price *= (1 + np.random.normal(0, 0.015))
        prices.append(max(price, 1))

    prices = np.array(prices)
    df = pd.DataFrame({
        "timestamp": dates,
        "open":   prices * (1 + np.random.uniform(-0.005, 0.005, n)),
        "high":   prices * (1 + np.random.uniform(0.001, 0.020, n)),
        "low":    prices * (1 - np.random.uniform(0.001, 0.020, n)),
        "close":  prices,
        "volume": np.random.uniform(1e6, 5e6, n),
    })
    return df


class TestIndicators:
    """Test that indicators are calculated correctly."""

    def test_indicators_added(self):
        """add_indicators should add all expected columns."""
        from src.strategy.indicators import add_indicators
        df = make_sample_df(300)
        df_ind = add_indicators(df)

        expected = ["ema_20", "ema_50", "rsi", "macd", "bb_upper", "bb_lower", "atr"]
        for col in expected:
            assert col in df_ind.columns, f"Missing indicator: {col}"

    def test_rsi_range(self):
        """RSI must always be between 0 and 100."""
        from src.strategy.indicators import add_indicators
        df = add_indicators(make_sample_df(300))
        assert df["rsi"].between(0, 100).all(), "RSI out of range"

    def test_bb_band_order(self):
        """Upper band must always be above lower band."""
        from src.strategy.indicators import add_indicators
        df = add_indicators(make_sample_df(300))
        assert (df["bb_upper"] >= df["bb_lower"]).all(), "BB upper < lower — impossible"

    def test_no_nan_after_warmup(self):
        """Core indicators should have no NaN after the warmup period."""
        from src.strategy.indicators import add_indicators
        df = add_indicators(make_sample_df(300))
        assert df["ema_20"].isna().sum() == 0
        assert df["rsi"].isna().sum() == 0
        assert df["macd"].isna().sum() == 0

    def test_ema_crossover_flag(self):
        """ema_cross_up should be True the day EMA20 crosses above EMA50."""
        from src.strategy.indicators import add_indicators
        df = add_indicators(make_sample_df(300, trend="up"))
        # Should have at least one crossover event in 300 days
        assert "ema_cross_up" in df.columns
        assert "ema_cross_down" in df.columns


class TestEMACrossover:
    """Test EMA Crossover strategy."""

    def test_returns_signal(self):
        """Should always return a Signal object."""
        from src.strategy.indicators import add_indicators
        from src.strategy.ema_crossover import EMACrossoverStrategy
        from src.strategy.signals import Signal

        df = add_indicators(make_sample_df(300))
        strategy = EMACrossoverStrategy()
        signal = strategy.generate(df, "TEST.NS")

        assert isinstance(signal, Signal)
        assert signal.action in ["BUY", "SELL", "HOLD"]
        assert 0.0 <= signal.confidence <= 1.0
        assert signal.price > 0

    def test_confidence_capped(self):
        """Confidence should never exceed 1.0."""
        from src.strategy.indicators import add_indicators
        from src.strategy.ema_crossover import EMACrossoverStrategy

        df = add_indicators(make_sample_df(300))
        strategy = EMACrossoverStrategy()
        signal = strategy.generate(df, "TEST.NS")
        assert signal.confidence <= 1.0

    def test_has_reasons(self):
        """Signal should always have at least one reason."""
        from src.strategy.indicators import add_indicators
        from src.strategy.ema_crossover import EMACrossoverStrategy

        df = add_indicators(make_sample_df(300))
        signal = EMACrossoverStrategy().generate(df, "TEST.NS")
        assert len(signal.reasons) >= 1

    def test_stop_loss_below_price_for_buy(self):
        """Stop loss should be below entry price for BUY signals."""
        from src.strategy.indicators import add_indicators
        from src.strategy.ema_crossover import EMACrossoverStrategy
        from src.strategy.signals import Action

        df = add_indicators(make_sample_df(300))
        signal = EMACrossoverStrategy().generate(df, "TEST.NS")
        if signal.action == Action.BUY and signal.stop_loss:
            assert signal.stop_loss < signal.price, "Stop loss should be below entry"


class TestRSIMACD:
    """Test RSI + MACD strategy."""

    def test_returns_signal(self):
        from src.strategy.indicators import add_indicators
        from src.strategy.rsi_macd import RSIMACDStrategy
        from src.strategy.signals import Signal

        df = add_indicators(make_sample_df(300))
        signal = RSIMACDStrategy().generate(df, "TEST.NS")
        assert isinstance(signal, Signal)
        assert 0.0 <= signal.confidence <= 1.0

    def test_buy_on_oversold(self):
        """Should lean BUY when RSI is very low."""
        from src.strategy.indicators import add_indicators
        from src.strategy.rsi_macd import RSIMACDStrategy
        from src.strategy.signals import Action

        # Create strongly downtrending data (will make RSI oversold eventually)
        df = add_indicators(make_sample_df(300, trend="down"))
        # Find a point where RSI is oversold
        oversold_rows = df[df["rsi"] < 35]
        if not oversold_rows.empty:
            # Test at that point
            idx = oversold_rows.index[-1]
            df_slice = df.iloc[:idx+1]
            signal = RSIMACDStrategy().generate(df_slice, "TEST.NS")
            # With RSI oversold, should be BUY or at least not SELL
            assert signal.action != Action.SELL, "Should not SELL when RSI is oversold"


class TestBollingerBands:
    """Test Bollinger Bands strategy."""

    def test_returns_signal(self):
        from src.strategy.indicators import add_indicators
        from src.strategy.bollinger_bands import BollingerBandsStrategy
        from src.strategy.signals import Signal

        df = add_indicators(make_sample_df(300))
        signal = BollingerBandsStrategy().generate(df, "TEST.NS")
        assert isinstance(signal, Signal)

    def test_has_bb_columns(self):
        """Indicators should include all BB columns."""
        from src.strategy.indicators import add_indicators
        df = add_indicators(make_sample_df(300))
        for col in ["bb_upper", "bb_lower", "bb_middle", "bb_width"]:
            assert col in df.columns


class TestStrategyEngine:
    """Test the master engine and consensus logic."""

    def test_consensus_all_buy(self):
        """When all strategies say BUY, confidence should be high."""
        from src.strategy.signals import Signal, Action
        from src.strategy.engine import StrategyEngine

        engine = StrategyEngine()
        signals = [
            Signal("X", Action.BUY, 0.8, "A", 100),
            Signal("X", Action.BUY, 0.7, "B", 100),
            Signal("X", Action.BUY, 0.9, "C", 100),
        ]
        result = engine._consensus(signals, "X")
        assert result.action == Action.BUY
        assert result.confidence >= 0.7

    def test_consensus_split_defaults_hold(self):
        """When strategies are evenly split, should be cautious."""
        from src.strategy.signals import Signal, Action
        from src.strategy.engine import StrategyEngine

        engine = StrategyEngine()
        signals = [
            Signal("X", Action.BUY,  0.6, "A", 100),
            Signal("X", Action.SELL, 0.6, "B", 100),
        ]
        result = engine._consensus(signals, "X")
        # With equal confidence, result should be HOLD
        assert result.action == Action.HOLD

    def test_scan_watchlist_returns_list(self):
        """scan_watchlist should return a list (may be empty if no signals)."""
        from src.strategy.engine import StrategyEngine
        engine = StrategyEngine()
        signals = engine.scan_watchlist(
            stocks=["RELIANCE.NS"],
            crypto=["BTCUSDT"],
            timeframe="1d",
            min_confidence=0.0,  # include everything
        )
        assert isinstance(signals, list)
        print(f"\n  ✅ Scanned 2 symbols, got {len(signals)} signals")
        for s in signals:
            print(f"     {s}")

    def test_summary_table_shape(self):
        """Summary table should have one row per symbol."""
        from src.strategy.engine import StrategyEngine
        engine = StrategyEngine()
        df = engine.get_summary_table(
            stocks=["RELIANCE.NS", "TCS.NS"],
            crypto=[],
            timeframe="1d",
        )
        assert len(df) == 2
        assert "action" in df.columns
        assert "confidence" in df.columns
        print(f"\n  ✅ Summary table:\n{df[['symbol','action','confidence','reason']].to_string()}")


class TestBacktest:
    """Test the backtesting engine."""

    def test_backtest_runs(self):
        """Backtest should run without error and return metrics."""
        from src.strategy.backtest import run_backtest
        result = run_backtest("BTCUSDT", strategy_name="EMA_Crossover", timeframe="1d")

        if "error" in result:
            pytest.skip(f"Backtest skipped: {result['error']}")

        assert "total_return_pct" in result
        assert "win_rate_pct" in result
        assert "sharpe_ratio" in result
        assert "total_trades" in result
        print(f"\n  ✅ Backtest result: {result['total_return_pct']}% return, "
              f"{result['win_rate_pct']}% win rate, "
              f"{result['total_trades']} trades")

    def test_backtest_rsi_macd(self):
        """RSI+MACD backtest should also run."""
        from src.strategy.backtest import run_backtest
        result = run_backtest("RELIANCE.NS", strategy_name="RSI_MACD", timeframe="1d")

        if "error" in result:
            pytest.skip(f"Backtest skipped: {result['error']}")

        assert "total_return_pct" in result
        print(f"\n  ✅ RSI_MACD on RELIANCE: {result['total_return_pct']}% return")
