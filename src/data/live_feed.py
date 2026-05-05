"""
src/data/live_feed.py
──────────────────────
Real-time price feed.

Crypto  : Binance WebSocket — streams live tick prices (sub-second)
Stocks  : yfinance 1-minute polling — checks every 60s during market hours

The feed maintains a live price cache that any part of the system
can read instantly without making an API call.

Usage:
    from src.data.live_feed import LiveFeed
    feed = LiveFeed()
    feed.start()                        # starts background threads
    price = feed.get_price("BTCUSDT")   # read cached live price
    price = feed.get_price("RELIANCE.NS")
    feed.stop()
"""

import threading
import time
from datetime import datetime, time as dtime
from src.utils.logger import logger


# NSE market hours (IST)
MARKET_OPEN  = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)

STOCK_SYMBOLS  = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]


class LiveFeed:
    """
    Maintains a live price cache updated in real time.
    Thread-safe — multiple readers, single writer per symbol.
    """

    def __init__(self):
        self._prices: dict[str, float]    = {}
        self._last_update: dict[str, datetime] = {}
        self._lock  = threading.Lock()
        self._running = False
        self._threads = []

    def start(self):
        """Start all live feed threads."""
        if self._running:
            return
        self._running = True

        # Crypto WebSocket thread
        t1 = threading.Thread(target=self._crypto_websocket_loop, daemon=True)
        t1.start()
        self._threads.append(t1)

        # Stock polling thread
        t2 = threading.Thread(target=self._stock_poll_loop, daemon=True)
        t2.start()
        self._threads.append(t2)

        logger.info("LiveFeed started — crypto WebSocket + stock polling active")

    def stop(self):
        """Stop all feed threads."""
        self._running = False
        logger.info("LiveFeed stopped")

    def get_price(self, symbol: str) -> float | None:
        """Get the latest cached live price for a symbol."""
        with self._lock:
            return self._prices.get(symbol)

    def get_all_prices(self) -> dict:
        """Get all cached live prices as a snapshot."""
        with self._lock:
            return dict(self._prices)

    def get_last_update(self, symbol: str) -> datetime | None:
        with self._lock:
            return self._last_update.get(symbol)

    def _set_price(self, symbol: str, price: float):
        """Thread-safe price update."""
        with self._lock:
            self._prices[symbol] = price
            self._last_update[symbol] = datetime.now()

    # ── Crypto: Binance WebSocket ─────────────────────────────────

    def _crypto_websocket_loop(self):
        """
        Streams live prices from Binance using WebSocket.
        Reconnects automatically on disconnect.
        """
        while self._running:
            try:
                self._connect_binance_ws()
            except Exception as e:
                logger.warning(f"Binance WebSocket error: {e} — reconnecting in 5s")
                time.sleep(5)

    def _connect_binance_ws(self):
        """Connect to Binance WebSocket and stream prices."""
        import websocket
        import json

        # Build stream URL for all symbols
        streams = "/".join(f"{s.lower()}@miniTicker" for s in CRYPTO_SYMBOLS)
        url = f"wss://stream.binance.com:9443/stream?streams={streams}"

        def on_message(ws, message):
            try:
                data = json.loads(message)
                ticker = data.get("data", {})
                symbol = ticker.get("s")
                price  = float(ticker.get("c", 0))
                if symbol and price:
                    self._set_price(symbol, price)
                    logger.debug(f"Live: {symbol} = ${price:,.2f}")
            except Exception as e:
                logger.debug(f"WS message parse error: {e}")

        def on_error(ws, error):
            logger.warning(f"Binance WS error: {error}")

        def on_close(ws, code, msg):
            logger.info("Binance WebSocket closed")

        def on_open(ws):
            logger.success("Binance WebSocket connected — live crypto prices streaming ✅")

        ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )
        ws.run_forever(ping_interval=30, ping_timeout=10)

    # ── Stocks: yfinance 1-minute polling ─────────────────────────

    def _stock_poll_loop(self):
        """
        Polls yfinance every 60 seconds for latest stock prices.
        Only runs during NSE market hours on weekdays.
        """
        while self._running:
            try:
                now = datetime.now()
                is_weekday     = now.weekday() < 5
                is_market_hours= MARKET_OPEN <= now.time() <= MARKET_CLOSE

                if is_weekday and is_market_hours:
                    self._poll_stocks()
                else:
                    # Outside market hours — use last known close price
                    self._fetch_stock_closes()

            except Exception as e:
                logger.warning(f"Stock poll error: {e}")

            time.sleep(60)  # Poll every 60 seconds

    def _poll_stocks(self):
        """Fetch latest 1-minute price for each stock."""
        import yfinance as yf
        for symbol in STOCK_SYMBOLS:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="1d", interval="1m")
                if not df.empty:
                    price = float(df["Close"].iloc[-1])
                    self._set_price(symbol, price)
                    logger.debug(f"Live: {symbol} = ₹{price:,.2f}")
            except Exception as e:
                logger.debug(f"Stock poll failed {symbol}: {e}")

    def _fetch_stock_closes(self):
        """Outside market hours — fetch last closing price once."""
        import yfinance as yf
        for symbol in STOCK_SYMBOLS:
            if symbol in self._prices:
                continue  # Already have a price cached
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="2d", interval="1d")
                if not df.empty:
                    price = float(df["Close"].iloc[-1])
                    self._set_price(symbol, price)
            except Exception as e:
                logger.debug(f"Close price failed {symbol}: {e}")


# Singleton — import and use anywhere
_feed_instance = None

def get_live_feed() -> LiveFeed:
    """Get the global LiveFeed singleton."""
    global _feed_instance
    if _feed_instance is None:
        _feed_instance = LiveFeed()
    return _feed_instance
