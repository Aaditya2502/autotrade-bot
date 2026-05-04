"""
src/execution/paper_trader.py
───────────────────────────────
Main paper trading engine.
Two separate loops:
  - Crypto : every 5 minutes  (Binance 15m candles)
  - Stocks : every 15 minutes (yfinance 1h candles)
"""

import time
from datetime import datetime
from src.execution.paper_portfolio import PaperPortfolio
from src.execution.trade_logger import TradeLogger
from src.strategy.engine import StrategyEngine
from src.strategy.signals import Action
from src.risk.manager import RiskManager
from src.risk.stop_loss import StopLossManager, StopType
from src.data.fetcher import DataFetcher
from src.data.yfinance_client import YFinanceClient
from src.data.binance_client import BinanceClient
from src.utils.logger import logger
from config.settings import settings
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler

STOCK_WATCHLIST  = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
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
        self.yf_client  = YFinanceClient()
        self.binance    = BinanceClient()
        self.cycle_count= 0
        logger.info(f"PaperTrader initialised | Capital: ₹{capital:,.0f}")

    # ── Unified cycle (used by dashboard startup) ─────────────────
    def run_cycle(self):
        """Run one full cycle for both stocks and crypto."""
        self.run_stock_cycle()
        self.run_crypto_cycle()

    # ── Stock cycle (every 15 min) ────────────────────────────────
    def run_stock_cycle(self):
        self.cycle_count += 1
        logger.info(f"📊 Stock cycle #{self.cycle_count} — {datetime.now().strftime('%H:%M:%S')}")
        self._check_open_positions(symbols=STOCK_WATCHLIST)
        self._scan_and_trade(
            symbols=STOCK_WATCHLIST,
            timeframe="1d",
            stop_type=StopType.FIXED,
        )
        self._print_cycle_summary()

    # ── Crypto cycle (every 5 min) ────────────────────────────────
    def run_crypto_cycle(self):
        logger.info(f"🪙  Crypto cycle — {datetime.now().strftime('%H:%M:%S')}")
        self._check_open_positions(symbols=CRYPTO_WATCHLIST)
        self._scan_and_trade(
            symbols=CRYPTO_WATCHLIST,
            timeframe="15m",
            stop_type=StopType.TRAILING,
        )

    # ── Check exits ───────────────────────────────────────────────
    def _check_open_positions(self, symbols: list):
        open_syms = [s for s in symbols if s in self.portfolio.positions]
        if not open_syms:
            return
        for symbol in open_syms:
            try:
                price = self._get_live_price(symbol)
                if not price:
                    continue
                self.portfolio.update_price(symbol, price)
                exit_signal = self.sl_manager.check_exits(symbol, price)
                if exit_signal:
                    trade = self.portfolio.close_position(
                        symbol=symbol,
                        exit_price=price,
                        reason=exit_signal.reason.value,
                    )
                    if trade:
                        self.logger.log_trade(trade)
                        self.risk.record_closed_trade(
                            pnl=trade.pnl,
                            capital=self.portfolio.total_value,
                        )
            except Exception as e:
                logger.error(f"Error checking {symbol}: {e}")

    # ── Scan and trade ────────────────────────────────────────────
    def _scan_and_trade(self, symbols: list, timeframe: str, stop_type: StopType):
        if len(self.portfolio.positions) >= settings.risk.max_open_positions:
            return

        is_stock = not symbols[0].endswith("USDT")
        if is_stock:
            signals = self.engine.scan_watchlist(
                stocks=symbols, crypto=[], timeframe=timeframe, min_confidence=0.0
            )
        else:
            signals = self.engine.scan_watchlist(
                stocks=[], crypto=symbols, timeframe=timeframe, min_confidence=0.0
            )

        signals.sort(key=lambda s: s.confidence, reverse=True)

        for signal in signals:
            if signal.symbol in self.portfolio.positions:
                continue

            decision = self.risk.evaluate_signal(
                signal,
                open_positions=len(self.portfolio.positions),
                total_exposure=sum(p.position_value for p in self.portfolio.positions.values()),
            )

            if not decision.approved:
                continue

            side = "long" if signal.action == Action.BUY else "short"
            success = self.portfolio.open_position(
                symbol=signal.symbol, side=side,
                quantity=decision.quantity, price=signal.price,
                stop_loss=decision.stop_loss, take_profit=decision.take_profit,
                strategy=signal.strategy,
            )

            if success:
                self.sl_manager.add_position(
                    symbol=signal.symbol, entry_price=signal.price,
                    stop_price=decision.stop_loss, take_profit=decision.take_profit,
                    direction=side, stop_type=stop_type,
                )
                if len(self.portfolio.positions) >= settings.risk.max_open_positions:
                    break

    # ── Live price ────────────────────────────────────────────────
    def _get_live_price(self, symbol: str):
        try:
            if symbol.endswith("USDT"):
                return float(self.binance.get_ticker(symbol)["price"])
            else:
                return self.yf_client.get_live_price(symbol)
        except Exception as e:
            logger.warning(f"Price fetch failed {symbol}: {e}")
            return None

    # ── Summary ───────────────────────────────────────────────────
    def _print_cycle_summary(self):
        s  = self.portfolio.get_summary()
        cb = self.risk.breaker.get_status_report()
        logger.info(
            f"Portfolio: ₹{s['current_value']:,.0f} ({s['total_pnl_pct']:+.2f}%) | "
            f"Cash: ₹{s['cash']:,.0f} | "
            f"Open: {s['open_positions']} | "
            f"Trades: {s['closed_trades']} | "
            f"Win: {s['win_rate_pct']:.0f}% | "
            f"Circuit: {cb['status'].upper()}"
        )

    def get_report(self) -> dict:
        s  = self.portfolio.get_summary()
        db = self.logger.get_stats()
        print(f"\n{'━'*55}")
        print(f"  PAPER TRADING REPORT")
        print(f"{'━'*55}")
        print(f"  Starting Capital : ₹{self.capital:>12,.0f}")
        print(f"  Current Value    : ₹{s['current_value']:>12,.0f}")
        print(f"  Total P&L        : ₹{s['total_pnl']:>+12,.0f}  ({s['total_pnl_pct']:+.2f}%)")
        print(f"  Realized P&L     : ₹{s['realized_pnl']:>+12,.0f}")
        print(f"  Total Trades     : {db.get('total_trades', 0)}")
        print(f"  Win Rate         : {db.get('win_rate_pct', 0):.1f}%")
        print(f"  Profit Factor    : {s.get('profit_factor', 0):.2f}")
        print(f"{'━'*55}\n")
        return {**s, **db}

    def start_loop(self, interval_minutes: int = 15, run_now: bool = True):
        logger.info("Starting dual-loop paper trader (stocks: 15m, crypto: 5m)")
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
        scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(self.run_stock_cycle,  "interval", minutes=15, id="stocks")
        scheduler.add_job(self.run_crypto_cycle, "interval", minutes=5,  id="crypto")
        scheduler.start()
        logger.info("Background dual-loop started (stocks: 15m, crypto: 5m)")
        return scheduler
