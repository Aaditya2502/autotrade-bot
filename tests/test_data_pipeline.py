"""
tests/test_data_pipeline.py
────────────────────────────
Tests for the Phase 2 data pipeline.
Run with:
    python -m pytest tests/test_data_pipeline.py -v
"""

import pytest
import pandas as pd


class TestYFinanceClient:
    """Test free NSE stock data fetching."""

    def test_fetch_reliance_daily(self):
        """Should fetch RELIANCE daily candles from NSE."""
        from src.data.yfinance_client import YFinanceClient
        client = YFinanceClient()
        df = client.get_historical("RELIANCE.NS", timeframe="1d", days=30)

        assert not df.empty, "Should return data for RELIANCE.NS"
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns
        assert "volume" in df.columns
        assert len(df) >= 15, "Should have at least 15 trading days in 30 calendar days"
        print(f"\n  ✅ RELIANCE.NS — {len(df)} candles fetched")
        print(f"     Latest close: ₹{df['close'].iloc[-1]:,.2f}")

    def test_fetch_tcs_daily(self):
        """Should fetch TCS daily candles."""
        from src.data.yfinance_client import YFinanceClient
        client = YFinanceClient()
        df = client.get_historical("TCS.NS", timeframe="1d", days=30)
        assert not df.empty
        print(f"\n  ✅ TCS.NS — {len(df)} candles, latest close: ₹{df['close'].iloc[-1]:,.2f}")

    def test_fetch_multiple_symbols(self):
        """Should fetch multiple symbols at once."""
        from src.data.yfinance_client import YFinanceClient
        client = YFinanceClient()
        results = client.get_multiple(
            ["INFY.NS", "HDFCBANK.NS"],
            timeframe="1d",
            days=30,
        )
        assert len(results) == 2, "Both symbols should return data"
        print(f"\n  ✅ Multi-fetch: {list(results.keys())}")

    def test_schema_is_correct(self):
        """DataFrame should have the correct columns and types."""
        from src.data.yfinance_client import YFinanceClient
        client = YFinanceClient()
        df = client.get_historical("RELIANCE.NS", timeframe="1d", days=10)

        assert "timestamp" in df.columns
        assert "symbol" in df.columns
        assert "exchange" in df.columns
        assert df["exchange"].iloc[0] == "NSE"
        assert pd.api.types.is_float_dtype(df["close"])
        assert df["close"].isna().sum() == 0, "No NaN close prices"

    def test_invalid_symbol_returns_empty(self):
        """Bad symbol should return empty DataFrame, not crash."""
        from src.data.yfinance_client import YFinanceClient
        client = YFinanceClient()
        df = client.get_historical("FAKESYMBOL999.NS", timeframe="1d", days=10)
        assert df.empty or len(df) == 0


class TestBinanceClient:
    """Test Binance crypto data fetching."""

    def test_fetch_btc_daily(self):
        """Should fetch BTC daily candles."""
        from src.data.binance_client import BinanceClient
        client = BinanceClient()
        df = client.get_historical("BTCUSDT", timeframe="1d", days=30)

        assert not df.empty
        assert len(df) >= 25
        print(f"\n  ✅ BTCUSDT — {len(df)} candles")
        print(f"     Latest close: ${df['close'].iloc[-1]:,.2f}")

    def test_fetch_eth_daily(self):
        """Should fetch ETH daily candles."""
        from src.data.binance_client import BinanceClient
        client = BinanceClient()
        df = client.get_historical("ETHUSDT", timeframe="1d", days=30)
        assert not df.empty
        print(f"\n  ✅ ETHUSDT — {len(df)} candles, latest: ${df['close'].iloc[-1]:,.2f}")


class TestDatabase:
    """Test DB storage and retrieval."""

    def test_init_db(self):
        """Database tables should be created without error."""
        from src.data.database import init_db
        init_db()  # Should not raise

    def test_fetch_and_store(self):
        """Should fetch candles and store them in DB."""
        from src.data.fetcher import DataFetcher
        fetcher = DataFetcher()

        count = fetcher.fetch_and_store("BTCUSDT", timeframe="1d", days=10)
        assert count >= 0, "Should store candles without error"
        print(f"\n  ✅ Stored {count} BTC candles in DB")

    def test_read_back_from_db(self):
        """Stored candles should be readable back from DB."""
        from src.data.fetcher import DataFetcher
        fetcher = DataFetcher()

        # Store some data first
        fetcher.fetch_and_store("ETHUSDT", timeframe="1d", days=10)

        # Read it back
        df = fetcher.get_candles("ETHUSDT", timeframe="1d", limit=100)
        assert not df.empty, "Should read back stored candles"
        assert "close" in df.columns
        print(f"\n  ✅ Read back {len(df)} ETH candles from DB")

    def test_duplicate_candles_not_stored(self):
        """Fetching the same data twice should not duplicate rows."""
        from src.data.fetcher import DataFetcher
        fetcher = DataFetcher()

        first  = fetcher.fetch_and_store("BTCUSDT", timeframe="1d", days=10)
        second = fetcher.fetch_and_store("BTCUSDT", timeframe="1d", days=10)

        # Second fetch should insert 0 new rows (all duplicates)
        assert second == 0, f"Expected 0 new rows on re-fetch, got {second}"
        print(f"\n  ✅ Duplicate prevention working — second fetch added {second} rows")

    def test_fetch_log_recorded(self):
        """Fetch log should record every fetch."""
        from src.data.fetcher import DataFetcher
        fetcher = DataFetcher()
        fetcher.fetch_and_store("SOLUSDT", timeframe="1d", days=5)

        log = fetcher.get_fetch_log()
        assert not log.empty
        sol_log = log[log["symbol"] == "SOLUSDT"]
        assert len(sol_log) > 0
        print(f"\n  ✅ Fetch log recorded for SOLUSDT: {sol_log['status'].iloc[0]}")
