"""
src/data/fetcher.py
────────────────────
Unified data fetcher.
Pulls from yfinance (stocks) + Binance (crypto),
normalises everything to the same schema,
and saves to the local SQLite database.

Usage:
    from src.data.fetcher import DataFetcher
    fetcher = DataFetcher()
    fetcher.fetch_and_store("RELIANCE.NS", timeframe="1d", days=365)
    fetcher.fetch_and_store("BTCUSDT",     timeframe="1d", days=365)
"""

import pandas as pd
from datetime import datetime
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.data.database import get_session, init_db, Candle, FetchLog
from src.data.yfinance_client import YFinanceClient
from src.data.binance_client import BinanceClient
from src.utils.logger import logger

# Symbols that should be fetched from Binance (crypto)
CRYPTO_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT"}


class DataFetcher:
    """
    Single entry point for all market data.
    Auto-routes to yfinance (stocks) or Binance (crypto).
    """

    def __init__(self):
        init_db()  # Create tables if not already there
        self.yf      = YFinanceClient()
        self.binance = BinanceClient()

    # ── Public API ────────────────────────────────────────────────

    def fetch_and_store(
        self,
        symbol: str,
        timeframe: str = "1d",
        days: int = 365,
    ) -> int:
        """
        Fetch OHLCV data for a symbol and save to DB.

        Returns:
            Number of new candles stored (duplicates are skipped)
        """
        logger.info(f"Starting fetch: {symbol} [{timeframe}]")

        try:
            # Route to the right data source
            if self._is_crypto(symbol):
                df = self.binance.get_historical(symbol, timeframe, days)
            else:
                df = self.yf.get_historical(symbol, timeframe, days)

            if df.empty:
                self._log_fetch(symbol, timeframe, 0, "empty", "No data returned")
                return 0

            stored = self._save_candles(df)
            self._log_fetch(symbol, timeframe, stored, "ok")
            logger.success(f"Stored {stored} new candles for {symbol} [{timeframe}]")
            return stored

        except Exception as e:
            logger.error(f"Fetch failed for {symbol}: {e}")
            self._log_fetch(symbol, timeframe, 0, "error", str(e))
            return 0

    def fetch_watchlist(
        self,
        stocks: list[str] = None,
        crypto: list[str] = None,
        timeframe: str = "1d",
        days: int = 365,
    ) -> dict:
        """
        Fetch a full watchlist of stocks + crypto in one call.

        Args:
            stocks   : NSE/BSE symbols e.g. ["RELIANCE.NS", "TCS.NS"]
            crypto   : Binance pairs e.g. ["BTCUSDT", "ETHUSDT"]
            timeframe: candle timeframe
            days     : history depth

        Returns:
            Summary dict with counts per symbol
        """
        stocks = stocks or []
        crypto = crypto or []
        all_symbols = stocks + crypto

        results = {}
        for symbol in all_symbols:
            count = self.fetch_and_store(symbol, timeframe, days)
            results[symbol] = count

        total = sum(results.values())
        logger.info(
            f"Watchlist fetch complete — "
            f"{len(all_symbols)} symbols, {total} total new candles"
        )
        return results

    def get_candles(
        self,
        symbol: str,
        timeframe: str = "1d",
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Read stored candles from DB for a symbol.

        Returns:
            DataFrame sorted by timestamp ascending
        """
        with get_session() as session:
            rows = (
                session.query(Candle)
                .filter(Candle.symbol == symbol, Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.desc())
                .limit(limit)
                .all()
            )

        if not rows:
            logger.warning(f"No candles found for {symbol} [{timeframe}] in DB")
            return pd.DataFrame()

        df = pd.DataFrame([{
            "timestamp": r.timestamp,
            "open":  r.open,
            "high":  r.high,
            "low":   r.low,
            "close": r.close,
            "volume": r.volume,
        } for r in rows])

        df.sort_values("timestamp", inplace=True)
        df.set_index("timestamp", inplace=True)
        return df

    def get_fetch_log(self) -> pd.DataFrame:
        """Show a summary of all fetches — useful for the dashboard."""
        with get_session() as session:
            rows = session.query(FetchLog).order_by(FetchLog.last_fetched.desc()).all()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame([{
            "symbol":       r.symbol,
            "timeframe":    r.timeframe,
            "last_fetched": r.last_fetched,
            "candles":      r.candle_count,
            "status":       r.status,
        } for r in rows])

    # ── Private helpers ───────────────────────────────────────────

    def _is_crypto(self, symbol: str) -> bool:
        return symbol.upper() in CRYPTO_SYMBOLS or symbol.upper().endswith("USDT")

    def _save_candles(self, df: pd.DataFrame) -> int:
        """
        Upsert candles into the DB.
        Skips duplicates (same symbol + timeframe + timestamp).
        Returns count of newly inserted rows.
        """
        df = df.reset_index()
        records = df.to_dict(orient="records")

        with get_session() as session:
            inserted = 0
            for row in records:
                stmt = (
                    sqlite_insert(Candle)
                    .values(
                        symbol    = str(row["symbol"]),
                        exchange  = str(row["exchange"]),
                        timeframe = str(row["timeframe"]),
                        timestamp = pd.to_datetime(row["timestamp"]),
                        open      = float(row["open"]),
                        high      = float(row["high"]),
                        low       = float(row["low"]),
                        close     = float(row["close"]),
                        volume    = float(row["volume"]),
                    )
                    .on_conflict_do_nothing(
                        index_elements=["symbol", "timeframe", "timestamp"]
                    )
                )
                result = session.execute(stmt)
                inserted += result.rowcount

            session.commit()

        return inserted

    def _log_fetch(
        self,
        symbol: str,
        timeframe: str,
        count: int,
        status: str,
        notes: str = None,
    ):
        """Upsert a fetch_log entry for this symbol+timeframe."""
        with get_session() as session:
            stmt = (
                sqlite_insert(FetchLog)
                .values(
                    symbol=symbol,
                    timeframe=timeframe,
                    last_fetched=datetime.now(),
                    candle_count=count,
                    status=status,
                    notes=notes,
                )
                .on_conflict_do_update(
                    index_elements=["symbol", "timeframe"],
                    set_=dict(
                        last_fetched=datetime.now(),
                        candle_count=count,
                        status=status,
                        notes=notes,
                    ),
                )
            )
            session.execute(stmt)
            session.commit()
