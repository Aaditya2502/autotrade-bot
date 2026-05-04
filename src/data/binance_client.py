"""
src/data/binance_client.py
───────────────────────────
Binance API wrapper for crypto market data.
Supports both testnet (safe) and mainnet (live).

SETUP STEPS:
  1. Go to https://www.binance.com → Account → API Management
  2. Create a new API key — enable ONLY "Read Info" (no withdrawals!)
  3. If using testnet: https://testnet.binance.vision — free fake funds
  4. Copy keys to .env as BINANCE_API_KEY and BINANCE_API_SECRET
"""

import pandas as pd
from datetime import datetime, timedelta
from binance.client import Client
from config.settings import settings
from src.utils.logger import logger


class BinanceClient:
    """Thin wrapper around python-binance for crypto OHLCV data."""

    TIMEFRAME_MAP = {
        "1m":  Client.KLINE_INTERVAL_1MINUTE,
        "5m":  Client.KLINE_INTERVAL_5MINUTE,
        "15m": Client.KLINE_INTERVAL_15MINUTE,
        "30m": Client.KLINE_INTERVAL_30MINUTE,
        "1h":  Client.KLINE_INTERVAL_1HOUR,
        "4h":  Client.KLINE_INTERVAL_4HOUR,
        "1d":  Client.KLINE_INTERVAL_1DAY,
        "1w":  Client.KLINE_INTERVAL_1WEEK,
    }

    def __init__(self):
        self.client = Client(
            api_key=settings.binance.api_key,
            api_secret=settings.binance.api_secret,
            testnet=settings.binance.testnet,
        )
        mode = "TESTNET" if settings.binance.testnet else "MAINNET"
        logger.info(f"BinanceClient initialised [{mode}]")

    # ── Market Data ───────────────────────────────────────────────

    def get_historical(
        self,
        symbol: str = "BTCUSDT",
        timeframe: str = "1d",
        days: int = 365,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV candles from Binance.

        Args:
            symbol:    e.g. "BTCUSDT", "ETHUSDT", "SOLUSDT"
            timeframe: "1m","5m","15m","30m","1h","4h","1d","1w"
            days:      how many calendar days back to fetch

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        interval = self.TIMEFRAME_MAP.get(timeframe)
        if not interval:
            raise ValueError(f"Invalid timeframe '{timeframe}'. Valid: {list(self.TIMEFRAME_MAP)}")

        start_str = (datetime.now() - timedelta(days=days)).strftime("%d %b %Y %H:%M:%S")
        logger.info(f"Fetching {symbol} [{timeframe}] — {days} days from Binance")

        raw = self.client.get_historical_klines(
            symbol=symbol,
            interval=interval,
            start_str=start_str,
        )

        df = pd.DataFrame(raw, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])

        # Keep only what we need
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df["symbol"] = symbol
        df["exchange"] = "BINANCE"
        df["timeframe"] = timeframe

        logger.success(f"Fetched {len(df)} candles for {symbol}")
        return df

    def get_ticker(self, symbol: str = "BTCUSDT") -> dict:
        """Get latest price for a symbol."""
        ticker = self.client.get_symbol_ticker(symbol=symbol)
        logger.debug(f"Ticker: {ticker}")
        return ticker

    def get_account_balance(self) -> pd.DataFrame:
        """Get current account balances (non-zero only)."""
        account = self.client.get_account()
        balances = [b for b in account["balances"] if float(b["free"]) > 0 or float(b["locked"]) > 0]
        df = pd.DataFrame(balances)
        df[["free", "locked"]] = df[["free", "locked"]].astype(float)
        return df
