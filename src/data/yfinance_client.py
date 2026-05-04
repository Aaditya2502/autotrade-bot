"""
src/data/yfinance_client.py
────────────────────────────
Free NSE/BSE stock data using yfinance.
No account or API key needed — works out of the box!

NSE symbol format : "RELIANCE.NS"
BSE symbol format : "RELIANCE.BO"

Common NSE symbols to try:
  Large Cap : RELIANCE.NS, TCS.NS, INFY.NS, HDFCBANK.NS, ICICIBANK.NS
  Mid Cap   : ZOMATO.NS, PAYTM.NS, NYKAA.NS
  Index ETF : NIFTYBEES.NS
"""

import yfinance as yf
import pandas as pd
from src.utils.logger import logger


# Maps our simple timeframe codes to yfinance interval strings
TIMEFRAME_MAP = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "30m": "30m",
    "1h":  "1h",
    "4h":  "4h",   # yfinance supports this
    "1d":  "1d",
    "1w":  "1wk",
}

# yfinance limits how far back you can go for intraday data
MAX_DAYS_INTRADAY = {
    "1m": 7, "5m": 60, "15m": 60, "30m": 60, "1h": 730,
}


class YFinanceClient:
    """Fetches historical OHLCV data from Yahoo Finance (free, no auth)."""

    def get_historical(
        self,
        symbol: str,
        timeframe: str = "1d",
        days: int = 365,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV candles for an NSE/BSE stock.

        Args:
            symbol   : Yahoo Finance symbol e.g. "RELIANCE.NS", "TCS.NS"
            timeframe: "1m","5m","15m","30m","1h","4h","1d","1w"
            days     : how many calendar days back to fetch

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
            plus metadata columns: symbol, exchange, timeframe
        """
        interval = TIMEFRAME_MAP.get(timeframe)
        if not interval:
            raise ValueError(f"Invalid timeframe '{timeframe}'. Valid: {list(TIMEFRAME_MAP)}")

        # Warn if asking for more days than yfinance allows for intraday
        if timeframe in MAX_DAYS_INTRADAY:
            max_days = MAX_DAYS_INTRADAY[timeframe]
            if days > max_days:
                logger.warning(
                    f"yfinance only supports {max_days} days for {timeframe} data. "
                    f"Capping at {max_days} days."
                )
                days = max_days

        period = f"{days}d"
        logger.info(f"Fetching {symbol} [{timeframe}] — {days} days via yfinance")

        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            logger.warning(f"No data returned for {symbol}. Check the symbol name.")
            return pd.DataFrame()

        # Normalise column names to lowercase
        df.columns = [c.lower() for c in df.columns]

        # Keep only what we need
        df = df[["open", "high", "low", "close", "volume"]].copy()

        # Clean up index
        df.index.name = "timestamp"
        df.index = pd.to_datetime(df.index)

        # Remove timezone info for consistent DB storage
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        df.reset_index(inplace=True)

        # Add metadata columns
        exchange = "BSE" if symbol.endswith(".BO") else "NSE"
        df["symbol"]    = symbol
        df["exchange"]  = exchange
        df["timeframe"] = timeframe

        # Drop rows with any NaN OHLCV values
        before = len(df)
        df.dropna(subset=["open", "high", "low", "close", "volume"], inplace=True)
        dropped = before - len(df)
        if dropped:
            logger.debug(f"Dropped {dropped} rows with NaN values for {symbol}")

        logger.success(f"Fetched {len(df)} candles for {symbol}")
        return df

    def get_multiple(
        self,
        symbols: list[str],
        timeframe: str = "1d",
        days: int = 365,
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch historical data for multiple symbols at once.

        Returns:
            Dict of {symbol: DataFrame}
        """
        results = {}
        for symbol in symbols:
            try:
                df = self.get_historical(symbol, timeframe, days)
                if not df.empty:
                    results[symbol] = df
            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
        logger.info(f"Fetched {len(results)}/{len(symbols)} symbols successfully")
        return results

    def get_live_price(self, symbol: str) -> float:
        """Get the latest closing price for a symbol."""
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d", interval="1m")
        if data.empty:
            raise ValueError(f"No live data for {symbol}")
        price = float(data["Close"].iloc[-1])
        logger.debug(f"Live price {symbol}: ₹{price:,.2f}")
        return price
