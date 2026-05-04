"""
src/execution/paper_trader.py
───────────────────────────────
Main paper trading engine.
Wires together:
  - Strategy Engine  (signals)
  - Risk Manager     (position sizing + circuit breaker)
  - Paper Portfolio  (virtual trades)
  - Trade Logger     (persistence)
  - Data Fetcher     (live prices)

One cycle = fetch prices → generate signals → evaluate risk → execute trades → check exits

Usage:
    from src.execution.paper_trader import PaperTrader
    trader = PaperTrader(capital=100_000)
    trader.run_cycle()          # Run one cycle manually
    trader.start_loop()         # Run every hour automatically
    trader.get_report()         # Print performance report
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


# ── Watchlists ────────────────────────────────────────────────────
STOCK_WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
]
CRYPTO_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
]


class PaperTrader:
    """
    Full paper trading engine.
    Simulates real trading with virtual money.
    """

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

    # ── Main cycle ────────────────────────────────────────────────

    def run_cycle(self):
        """
        Run one full trading cycle:
        1. Update prices on open positions
        2. Check stop losses / take profits
        3. Scan for new signals
        4. Evaluate signals through risk manager
        5. Execute approved trades
        """
        self.cycle_count += 1
        logger.info(f"\n{'═'*55}")
        logger.info(f"  Paper Trading Cycle #{self.cycle_count} — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"{'═'*55}")

        # Step 1: Update prices + check exits on open positions
        self._check_open_positions()

        # Step 2: Scan for new signals
        self._scan_and_trade()

        # Step 3: Print cycle summary
        self._print_cycle_summary()

    # ── Private: position management ─────────────────────────────

    def _check_open_positions(self):
        """Update prices and check stop loss / take profit for all open positions."""
        if not self.portfolio.positions:
            return

        logger.info(f"Checking {len(self.portfolio.positions)} open positions...")

        for symbol, position in list(self.portfolio.positions.items()):
            try:
                # Get latest price
                current_price = self._get_live_price(symbol)
                if not current_price:
                    continue

                self.portfolio.update_price(symbol, current_price)

                # Check if stop loss or take profit hit
                exit_signal = self.sl_manager.check_exits(symbol, current_price)
                if exit_signal:
                    trade = self.portfolio.close_position(
                        symbol=symbol,
                        exit_price=current_price,
                        reason=exit_signal.reason.value,
                    )
                    if trade:
                        self.logger.log_trade(trade)
                        self.risk.record_closed_trade(
                            pnl=trade.pnl,
                            capital=self.portfolio.total_value
                        )
                else:
                    logger.debug(
                        f"  {symbol}: ₹{current_price:,.2f} | "
                        f"P&L: {position.unrealized_pnl_pct:+.2f}%"
                    )

            except Exception as e:
                logger.error(f"Error checking position {symbol}: {e}")

    # ── Private: signal scanning ──────────────────────────────────

    def _scan_and_trade(self):
        """Scan watchlist, evaluate signals, and execute approved trades."""

        # Don't open more positions if we're at the limit
        if len(self.portfolio.positions) >= settings.risk.max_open_positions:
            logger.info("Max positions reached — skipping new signal scan")
            return

        # Get signals — use 1h for crypto, 1d for stocks
        stock_signals = self.engine.scan_watchlist(
            stocks=STOCK_WATCHLIST, crypto=[],
            timeframe="1d", min_confidence=0.0,
        )
        crypto_signals = self.engine.scan_watchlist(
            stocks=[], crypto=CRYPTO_WATCHLIST,
            timeframe="1h", min_confidence=0.0,
        )
        all_signals = stock_signals + crypto_signals

        # Sort by confidence descending — take best signals first
        all_signals.sort(key=lambda s: s.confidence, reverse=True)

        executed = 0
        for signal in all_signals:
            # Skip symbols we already hold
            if signal.symbol in self.portfolio.positions:
                continue

            # Evaluate through risk manager
            open_count  = len(self.portfolio.positions)
            total_exp   = sum(p.position_value for p in self.portfolio.positions.values())
            decision    = self.risk.evaluate_signal(
                signal,
                open_positions=open_count,
                total_exposure=total_exp,
            )

            if not decision.approved:
                logger.debug(f"Rejected: {signal.symbol} — {decision.rejection_reason}")
                continue

            # Execute the paper trade
            side = "long" if signal.action == Action.BUY else "short"
            success = self.portfolio.open_position(
                symbol      = signal.symbol,
                side        = side,
                quantity    = decision.quantity,
                price       = signal.price,
                stop_loss   = decision.stop_loss,
                take_profit = decision.take_profit,
                strategy    = signal.strategy,
            )

            if success:
                # Register stop loss with the manager
                self.sl_manager.add_position(
                    symbol      = signal.symbol,
                    entry_price = signal.price,
                    stop_price  = decision.stop_loss,
                    take_profit = decision.take_profit,
                    direction   = side,
                    stop_type   = StopType.TRAILING if "1h" in signal.strategy else StopType.FIXED,
                )
                executed += 1

                # Stop after filling positions
                if len(self.portfolio.positions) >= settings.risk.max_open_positions:
                    break

        if executed == 0:
            logger.info("No new trades executed this cycle — market conditions not favourable")

    # ── Private: price fetching ───────────────────────────────────

    def _get_live_price(self, symbol: str) -> float | None:
        """Get the latest price for a symbol."""
        try:
            if symbol.endswith("USDT"):
                ticker = self.binance.get_ticker(symbol)
                return float(ticker["price"])
            else:
                return self.yf_client.get_live_price(symbol)
        except Exception as e:
            logger.warning(f"Could not get live price for {symbol}: {e}")
            return None

    # ── Reporting ─────────────────────────────────────────────────

    def _print_cycle_summary(self):
        """Print a quick summary after each cycle."""
        summary = self.portfolio.get_summary()
        cb      = self.risk.breaker.get_status_report()

        logger.info(f"\n{'─'*55}")
        logger.info(f"  Portfolio Summary:")
        logger.info(f"  Value:        ₹{summary['current_value']:>12,.2f}  ({summary['total_pnl_pct']:+.2f}%)")
        logger.info(f"  Cash:         ₹{summary['cash']:>12,.2f}")
        logger.info(f"  Open:         {summary['open_positions']} positions")
        logger.info(f"  Closed:       {summary['closed_trades']} trades  | Win rate: {summary['win_rate_pct']:.0f}%")
        logger.info(f"  Realized P&L: ₹{summary['realized_pnl']:>+12,.2f}")
        logger.info(f"  Circuit:      {cb['status'].upper()}")
        logger.info(f"{'─'*55}")

    def get_report(self) -> dict:
        """Get full performance report."""
        portfolio_summary = self.portfolio.get_summary()
        db_stats          = self.logger.get_stats()
        risk_report       = self.risk.get_risk_report()

        print(f"\n{'━'*60}")
        print(f"  📊 PAPER TRADING PERFORMANCE REPORT")
        print(f"{'━'*60}")
        print(f"  Starting Capital:  ₹{self.capital:>12,.2f}")
        print(f"  Current Value:     ₹{portfolio_summary['current_value']:>12,.2f}")
        print(f"  Total P&L:         ₹{portfolio_summary['total_pnl']:>+12,.2f}  ({portfolio_summary['total_pnl_pct']:+.2f}%)")
        print(f"  Realized P&L:      ₹{portfolio_summary['realized_pnl']:>+12,.2f}")
        print(f"  Unrealized P&L:    ₹{portfolio_summary['unrealized_pnl']:>+12,.2f}")
        print(f"{'─'*60}")
        print(f"  Total Trades:      {db_stats.get('total_trades', 0)}")
        print(f"  Win Rate:          {db_stats.get('win_rate_pct', 0):.1f}%")
        print(f"  Avg Win:           ₹{db_stats.get('avg_win', 0):>+,.2f}")
        print(f"  Avg Loss:          ₹{db_stats.get('avg_loss', 0):>+,.2f}")
        print(f"  Best Trade:        ₹{db_stats.get('best_trade', 0):>+,.2f}")
        print(f"  Worst Trade:       ₹{db_stats.get('worst_trade', 0):>+,.2f}")
        print(f"  Profit Factor:     {portfolio_summary.get('profit_factor', 0):.2f}")
        print(f"{'─'*60}")
        print(f"  Open Positions:    {portfolio_summary['open_positions']}")
        if self.portfolio.positions:
            for sym, pos in self.portfolio.positions.items():
                print(f"    {sym:<15} {pos.side:<5} {pos.quantity} × ₹{pos.current_price:,.2f} | P&L: {pos.unrealized_pnl_pct:+.2f}%")
        print(f"{'━'*60}\n")

        return {**portfolio_summary, **db_stats}

    # ── Scheduler ─────────────────────────────────────────────────

    def start_loop(self, interval_minutes: int = 60, run_now: bool = True):
        """
        Start the paper trading loop.
        Runs run_cycle() every interval_minutes.
        Press Ctrl+C to stop.
        """
        logger.info(f"Starting paper trading loop — every {interval_minutes} minutes")
        logger.info("Press Ctrl+C to stop\n")

        if run_now:
            self.run_cycle()

        scheduler = BlockingScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(
            func=self.run_cycle,
            trigger="interval",
            minutes=interval_minutes,
            id="paper_trade_cycle",
        )

        try:
            scheduler.start()
        except KeyboardInterrupt:
            logger.info("Paper trading loop stopped by user")
            self.get_report()

    def start_background(self, interval_minutes: int = 60):
        """Start paper trading in the background (non-blocking)."""
        scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(
            func=self.run_cycle,
            trigger="interval",
            minutes=interval_minutes,
            id="paper_trade_cycle",
        )
        scheduler.start()
        logger.info(f"Background paper trading started — every {interval_minutes} min")
        return scheduler


# ── Telegram integration (added in Phase 6) ───────────────────────
def _setup_alerts(self):
    from src.alerts.telegram_bot import TelegramAlert
    self.alerts = TelegramAlert()

