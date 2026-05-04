"""
src/data/scheduler.py
──────────────────────
Scheduled data refresh using APScheduler.
Keeps the local DB up to date without manual fetching.

Schedules:
  - Daily candles  : every day at 6:30am IST (after NSE market open)
  - Hourly candles : every hour during market hours
  - Crypto         : every 15 minutes (crypto never sleeps!)

Usage:
    from src.data.scheduler import DataScheduler
    scheduler = DataScheduler()
    scheduler.start()         # Start background refresh
    scheduler.stop()          # Stop gracefully
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.data.fetcher import DataFetcher
from src.utils.logger import logger


# ── Watchlist — edit these to add/remove symbols ─────────────────

STOCK_WATCHLIST = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "WIPRO.NS",
    "BAJFINANCE.NS",
    "NIFTYBEES.NS",   # Nifty 50 ETF — great for index tracking
]

CRYPTO_WATCHLIST = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
]


class DataScheduler:
    """Runs background jobs to keep the DB fresh."""

    def __init__(self):
        self.fetcher   = DataFetcher()
        self.scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        self._register_jobs()

    def _register_jobs(self):
        # ── Daily stock candles ───────────────────────────────────
        # Runs at 6:30am IST — 15 minutes after NSE opens
        self.scheduler.add_job(
            func=self._refresh_daily_stocks,
            trigger=CronTrigger(hour=6, minute=30, timezone="Asia/Kolkata"),
            id="daily_stocks",
            name="Daily NSE/BSE candles",
            replace_existing=True,
        )

        # ── Hourly stock candles (market hours only) ──────────────
        # 9:15am to 3:30pm IST on weekdays
        self.scheduler.add_job(
            func=self._refresh_hourly_stocks,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour="9-15",
                minute=20,
                timezone="Asia/Kolkata",
            ),
            id="hourly_stocks",
            name="Hourly NSE/BSE candles",
            replace_existing=True,
        )

        # ── Crypto — every 15 minutes, 24/7 ─────────────────────
        self.scheduler.add_job(
            func=self._refresh_crypto,
            trigger=IntervalTrigger(minutes=15),
            id="crypto_15m",
            name="Crypto 15m candles",
            replace_existing=True,
        )

        logger.info("Scheduled jobs registered:")
        logger.info("  • Daily stocks   — 6:30am IST")
        logger.info("  • Hourly stocks  — 9:20am–3:20pm IST (weekdays)")
        logger.info("  • Crypto         — every 15 minutes")

    # ── Job functions ─────────────────────────────────────────────

    def _refresh_daily_stocks(self):
        logger.info("⏰ Scheduled job: Daily stock refresh")
        self.fetcher.fetch_watchlist(
            stocks=STOCK_WATCHLIST,
            timeframe="1d",
            days=365,
        )

    def _refresh_hourly_stocks(self):
        logger.info("⏰ Scheduled job: Hourly stock refresh")
        self.fetcher.fetch_watchlist(
            stocks=STOCK_WATCHLIST,
            timeframe="1h",
            days=30,
        )

    def _refresh_crypto(self):
        logger.info("⏰ Scheduled job: Crypto 15m refresh")
        self.fetcher.fetch_watchlist(
            crypto=CRYPTO_WATCHLIST,
            timeframe="15m",
            days=30,
        )

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self):
        """Start the scheduler in the background."""
        self.scheduler.start()
        logger.success("DataScheduler started — background refresh active ✅")

    def stop(self):
        """Shut down the scheduler cleanly."""
        self.scheduler.shutdown(wait=False)
        logger.info("DataScheduler stopped")

    def run_initial_fetch(self):
        """
        Manually trigger a full fetch right now.
        Call this once on first run to populate the DB.
        """
        logger.info("Running initial full data fetch...")

        # 1 year of daily candles for everything
        self.fetcher.fetch_watchlist(
            stocks=STOCK_WATCHLIST,
            crypto=CRYPTO_WATCHLIST,
            timeframe="1d",
            days=365,
        )

        # 60 days of hourly candles
        self.fetcher.fetch_watchlist(
            stocks=STOCK_WATCHLIST,
            crypto=CRYPTO_WATCHLIST,
            timeframe="1h",
            days=60,
        )

        logger.success("Initial fetch complete! DB is populated ✅")
