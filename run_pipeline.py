"""
run_pipeline.py
────────────────
Quick script to populate your DB with real market data.
Run this manually after setup:

    python run_pipeline.py

What it does:
  1. Initialises the database
  2. Fetches 1 year of daily candles for all watchlist symbols
  3. Fetches 60 days of hourly candles
  4. Prints a summary table

Edit STOCKS and CRYPTO below to customise your watchlist.
"""

from src.data.database import init_db
from src.data.fetcher import DataFetcher
from src.utils.logger import logger

# ── Your Watchlist — edit freely ─────────────────────────────────

STOCKS = [
    "RELIANCE.NS",   # Reliance Industries
    "TCS.NS",        # Tata Consultancy Services
    "INFY.NS",       # Infosys
    "HDFCBANK.NS",   # HDFC Bank
    "ICICIBANK.NS",  # ICICI Bank
]

CRYPTO = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
]

# ─────────────────────────────────────────────────────────────────

def main():
    print("\n" + "━" * 55)
    print("  AutoTrade — Data Pipeline Initial Fetch")
    print("━" * 55)

    # Step 1: Init DB
    logger.info("Initialising database...")
    init_db()

    fetcher = DataFetcher()

    # Step 2: Daily candles — 1 year
    print("\n📅  Fetching 1 year of DAILY candles...")
    daily_results = fetcher.fetch_watchlist(
        stocks=STOCKS,
        crypto=CRYPTO,
        timeframe="1d",
        days=365,
    )

    # Step 3: Hourly candles — 60 days
    print("\n⏱️   Fetching 60 days of HOURLY candles...")
    hourly_results = fetcher.fetch_watchlist(
        stocks=STOCKS,
        crypto=CRYPTO,
        timeframe="1h",
        days=60,
    )

    # Step 4: Summary
    print("\n" + "━" * 55)
    print("  ✅ Fetch Complete! Summary:")
    print("━" * 55)

    log = fetcher.get_fetch_log()
    if not log.empty:
        print(log.to_string(index=False))

    print("\n" + "━" * 55)
    print("  Your DB is now populated with real market data!")
    print("  Next: run the tests to verify everything:")
    print("  python -m pytest tests/test_data_pipeline.py -v")
    print("━" * 55 + "\n")


if __name__ == "__main__":
    main()
