"""
src/data/kite_client.py
────────────────────────
Zerodha Kite API wrapper.
Handles authentication, historical data fetch, and live quotes for NSE/BSE.

SETUP STEPS (do once):
  1. Go to https://kite.trade and create an app
  2. Copy API key + secret into .env
  3. Run `python -m src.data.kite_client --login` to get your access token
  4. Paste the access token into .env as KITE_ACCESS_TOKEN
  Note: Access token expires every day at 6am IST — needs daily refresh.
"""

import argparse
import pandas as pd
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from config.settings import settings
from src.utils.logger import logger


class KiteClient:
    """Thin wrapper around KiteConnect for market data."""

    TIMEFRAME_MAP = {
        "1m":  "minute",
        "5m":  "5minute",
        "15m": "15minute",
        "30m": "30minute",
        "1h":  "60minute",
        "1d":  "day",
    }

    def __init__(self):
        self.kite = KiteConnect(api_key=settings.kite.api_key)
        if settings.kite.access_token:
            self.kite.set_access_token(settings.kite.access_token)
            logger.info("KiteClient initialised with existing access token")
        else:
            logger.warning("No Kite access token set — call login() first")

    # ── Authentication ────────────────────────────────────────────

    def get_login_url(self) -> str:
        """Returns the URL the user must visit to authorise the app."""
        return self.kite.login_url()

    def generate_access_token(self, request_token: str) -> str:
        """Exchange request_token for access_token after user login."""
        data = self.kite.generate_session(request_token, api_secret=settings.kite.api_secret)
        access_token = data["access_token"]
        logger.success(f"Access token generated: {access_token[:10]}...")
        logger.info("Paste this into .env as KITE_ACCESS_TOKEN")
        return access_token

    # ── Market Data ───────────────────────────────────────────────

    def get_historical(
        self,
        symbol: str,
        exchange: str = "NSE",
        timeframe: str = "1d",
        days: int = 365,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data for a stock.

        Args:
            symbol:    e.g. "RELIANCE", "TCS", "INFY"
            exchange:  "NSE" or "BSE"
            timeframe: "1m","5m","15m","30m","1h","1d"
            days:      how many calendar days back to fetch

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        interval = self.TIMEFRAME_MAP.get(timeframe)
        if not interval:
            raise ValueError(f"Invalid timeframe '{timeframe}'. Valid: {list(self.TIMEFRAME_MAP)}")

        instrument_token = self._get_instrument_token(symbol, exchange)
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        logger.info(f"Fetching {symbol}/{exchange} [{timeframe}] — {days} days")

        raw = self.kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
        )

        df = pd.DataFrame(raw)
        df.rename(columns={"date": "timestamp"}, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        df["symbol"] = symbol
        df["exchange"] = exchange
        df["timeframe"] = timeframe

        logger.success(f"Fetched {len(df)} candles for {symbol}")
        return df

    def get_quote(self, symbols: list[str], exchange: str = "NSE") -> dict:
        """Get live quote for one or more symbols."""
        instruments = [f"{exchange}:{s}" for s in symbols]
        quotes = self.kite.quote(instruments)
        logger.debug(f"Live quotes fetched for: {symbols}")
        return quotes

    # ── Instruments ───────────────────────────────────────────────

    def _get_instrument_token(self, symbol: str, exchange: str) -> int:
        """Look up instrument token for a symbol."""
        instruments = self.kite.instruments(exchange)
        matches = [i for i in instruments if i["tradingsymbol"] == symbol]
        if not matches:
            raise ValueError(f"Symbol '{symbol}' not found on {exchange}")
        return matches[0]["instrument_token"]


# ── CLI helper for first-time login ──────────────────────────────

def cli_login():
    """Walk the user through getting an access token."""
    client = KiteClient()
    print("\n📌 Step 1: Open this URL in your browser and login with your Zerodha account:")
    print(f"\n  {client.get_login_url()}\n")
    request_token = input("📌 Step 2: Paste the request_token from the redirect URL: ").strip()
    access_token = client.generate_access_token(request_token)
    print(f"\n✅ Your access token: {access_token}")
    print("📌 Add this to your .env file as: KITE_ACCESS_TOKEN=" + access_token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", action="store_true", help="Get a fresh Kite access token")
    args = parser.parse_args()
    if args.login:
        cli_login()
