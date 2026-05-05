"""
src/execution/paper_trader.py
Paper trading engine with live price feed.

Three loops:
  1. Live feed      — real-time prices (WebSocket + 1min polling)
  2. Stop loss loop — checks exits every 30 seconds using live prices
  3. Signal loops   — crypto every 5 min, stocks every 15 min
"""

import time
from datetime import datetime
from src.execution.paper_portfolio import PaperPortfolio
from src.execution.trade_logger    import TradeLogger
from src.strategy.engine           import StrategyEngine
from src.strategy.signals          import Action
from src.risk.manager              import RiskManager
from src.risk.stop_loss            import StopLossManager, StopType
from src.data.fetcher              import DataFetcher
from src.data.live_feed            import LiveFeed
from src.utils.logger              import logger
from config.settings               import settings
from apscheduler.schedulers.blocking   import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler

STOCK_WATCHLIST  = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "ZOMATO.NS", "TATAMOTORS.NS", "WIPRO.NS", "BAJFINANCE.NS", "NIFTYBEES.NS"]
CRYPTO_WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]


class PaperTrader:

    def __init__(self, capital: float = 100_000):
        self.capital    = capital
        self.portfolio  = PaperPortfolio(starting_capital=capital)
        self.risk       = RiskManager(capital=capital)
        self.sl_manager = StopLossManager()
        self.engine     = StrategyEngine()
        self.logger     = TradeLogger()
        self.fetcher    = DataFetcher()
        self.live_feed  = LiveFeed()
        self.cycle_count= 0
        self.live_feed.start()
        logger.info(f"PaperTrader initialised | Capital: ₹{capital:,.0f} | Live feed: ON")

    def start_live_monitor(self):
        """Background thread — checks stop losses every 30 seconds using live prices."""
        import threading
        t = threading.Thread(target=self._live_sl_loop, daemon=True)
        t.start()
        logger.info("Live stop-loss monitor started (every 30 sec)")

    def _live_sl_loop(self):
        while True:
            try:
                for symbol in list(self.portfolio.positions.keys()):
                    price = self.live_feed.get_price(symbol)
                    if price:
                        self.portfolio.update_price(symbol, price)
                        exit_signal = self.sl_manager.check_exits(symbol, price)
                        if exit_signal:
                            trade = self.portfolio.close_position(
                                symbol=symbol, exit_price=price,
                                reason=exit_signal.reason.value,
                            )
                            if trade:
                                self.logger.log_trade(trade)
                                self.risk.record_closed_trade(
                                    pnl=trade.pnl,
                                    capital=self.portfolio.total_value,
                                )
                                logger.info(
                                    f"LIVE EXIT: {symbol} @ ₹{price:,.2f} | "
                                    f"P&L: ₹{trade.pnl:+,.2f} ({trade.pnl_pct:+.2f}%)"
                                )
            except Exception as e:
                logger.error(f"Live SL error: {e}")
            time.sleep(30)

    def run_cycle(self):
        self.run_stock_cycle()
        self.run_crypto_cycle()

    def run_stock_cycle(self):
        self.cycle_count += 1
        logger.info(f"Stock cycle #{self.cycle_count} — {datetime.now().strftime('%H:%M:%S')}")
        self._check_open_positions(STOCK_WATCHLIST)
        self._scan_and_trade(STOCK_WATCHLIST, "1d", StopType.FIXED)
        self._print_cycle_summary()

    def run_crypto_cycle(self):
        logger.info(f"Crypto cycle — {datetime.now().strftime('%H:%M:%S')}")
        self._check_open_positions(CRYPTO_WATCHLIST)
        self._scan_and_trade(CRYPTO_WATCHLIST, "15m", StopType.TRAILING)

    def _check_open_positions(self, symbols: list):
        for symbol in [s for s in symbols if s in self.portfolio.positions]:
            try:
                price = self.live_feed.get_price(symbol) or self._fallback_price(symbol)
                if not price:
                    continue
                self.portfolio.update_price(symbol, price)
                exit_signal = self.sl_manager.check_exits(symbol, price)
                if exit_signal:
                    trade = self.portfolio.close_position(
                        symbol=symbol, exit_price=price,
                        reason=exit_signal.reason.value,
                    )
                    if trade:
                        self.logger.log_trade(trade)
                        self.risk.record_closed_trade(
                            pnl=trade.pnl, capital=self.portfolio.total_value,
                        )
            except Exception as e:
                logger.error(f"Error checking {symbol}: {e}")

    def _scan_and_trade(self, symbols: list, timeframe: str, stop_type: StopType):
        if len(self.portfolio.positions) >= settings.risk.max_open_positions:
            return

        is_stock = not symbols[0].endswith("USDT")
        signals  = self.engine.scan_watchlist(
            stocks=symbols if is_stock else [],
            crypto=symbols if not is_stock else [],
            timeframe=timeframe, min_confidence=0.0,
        )
        signals.sort(key=lambda s: s.confidence, reverse=True)

        for signal in signals:
            if signal.symbol in self.portfolio.positions:
                continue
            live_price = self.live_feed.get_price(signal.symbol)
            if live_price:
                signal.price = live_price  # use live price as entry

            decision = self.risk.evaluate_signal(
                signal,
                open_positions=len(self.portfolio.positions),
                total_exposure=sum(p.position_value for p in self.portfolio.positions.values()),
            )
            if not decision.approved:
                continue

            side = "long" if signal.action == Action.BUY else "short"
            if self.portfolio.open_position(
                symbol=signal.symbol, side=side,
                quantity=decision.quantity, price=signal.price,
                stop_loss=decision.stop_loss, take_profit=decision.take_profit,
                strategy=signal.strategy,
            ):
                self.sl_manager.add_position(
                    symbol=signal.symbol, entry_price=signal.price,
                    stop_price=decision.stop_loss, take_profit=decision.take_profit,
                    direction=side, stop_type=stop_type,
                )
            if len(self.portfolio.positions) >= settings.risk.max_open_positions:
                break

    def _fallback_price(self, symbol: str) -> float | None:
        try:
            if symbol.endswith("USDT"):
                from src.data.binance_client import BinanceClient
                return float(BinanceClient().get_ticker(symbol)["price"])
            from src.data.yfinance_client import YFinanceClient
            return YFinanceClient().get_live_price(symbol)
        except:
            return None

    def _print_cycle_summary(self):
        s  = self.portfolio.get_summary()
        cb = self.risk.breaker.get_status_report()
        logger.info(
            f"Value: ₹{s['current_value']:,.0f} ({s['total_pnl_pct']:+.2f}%) | "
            f"Cash: ₹{s['cash']:,.0f} | Open: {s['open_positions']} | "
            f"Win: {s['win_rate_pct']:.0f}% | Circuit: {cb['status'].upper()}"
        )

    def get_report(self) -> dict:
        s  = self.portfolio.get_summary()
        db = self.logger.get_stats()
        print(f"\n{'━'*55}")
        print(f"  Starting Capital : ₹{self.capital:>12,.0f}")
        print(f"  Current Value    : ₹{s['current_value']:>12,.0f}")
        print(f"  Total P&L        : ₹{s['total_pnl']:>+12,.0f}  ({s['total_pnl_pct']:+.2f}%)")
        print(f"  Total Trades     : {db.get('total_trades', 0)}")
        print(f"  Win Rate         : {db.get('win_rate_pct', 0):.1f}%")
        print(f"{'━'*55}\n")
        return {**s, **db}

    def start_loop(self, run_now: bool = True):
        self.start_live_monitor()
        if run_now:
            self.run_cycle()
        scheduler = BlockingScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(self.run_stock_cycle,  "interval", minutes=15, id="stocks")
        scheduler.add_job(self.run_crypto_cycle, "interval", minutes=5,  id="crypto")
        try:
            scheduler.start()
        except KeyboardInterrupt:
            self.get_report()

    def start_background(self):
        self.start_live_monitor()
        scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(self.run_stock_cycle,  "interval", minutes=15, id="stocks")
        scheduler.add_job(self.run_crypto_cycle, "interval", minutes=5,  id="crypto")
        scheduler.start()
        return scheduler
