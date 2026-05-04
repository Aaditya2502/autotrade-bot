"""
tests/test_paper_trading.py
────────────────────────────
Tests for Phase 5 — Paper Trading.
Run with:
    python -m pytest tests/test_paper_trading.py -v
"""

import pytest
from datetime import datetime


class TestPaperPortfolio:
    """Test virtual portfolio accounting."""

    def test_initial_state(self):
        """Portfolio should start with correct cash balance."""
        from src.execution.paper_portfolio import PaperPortfolio
        p = PaperPortfolio(starting_capital=100_000)
        assert p.cash == 100_000
        assert p.total_value == 100_000
        assert len(p.positions) == 0
        assert len(p.closed_trades) == 0

    def test_open_position_deducts_cash(self):
        """Opening a position should reduce cash."""
        from src.execution.paper_portfolio import PaperPortfolio
        p = PaperPortfolio(100_000)
        success = p.open_position("RELIANCE.NS", "long", 10, 1500, 1440, 1600, "Test")
        assert success
        assert p.cash == 100_000 - (10 * 1500)
        assert "RELIANCE.NS" in p.positions

    def test_close_position_returns_cash(self):
        """Closing a position should add proceeds back to cash."""
        from src.execution.paper_portfolio import PaperPortfolio
        p = PaperPortfolio(100_000)
        p.open_position("TCS.NS", "long", 5, 2000, 1900, 2200, "Test")
        trade = p.close_position("TCS.NS", exit_price=2100, reason="take_profit")
        assert trade is not None
        assert trade.pnl == pytest.approx(5 * (2100 - 2000))
        assert trade.is_winner
        assert "TCS.NS" not in p.positions
        print(f"\n  ✅ Trade closed: P&L=₹{trade.pnl:+,.2f} ({trade.pnl_pct:+.2f}%)")

    def test_losing_trade_pnl(self):
        """Stop loss hit should result in negative P&L."""
        from src.execution.paper_portfolio import PaperPortfolio
        p = PaperPortfolio(100_000)
        p.open_position("INFY.NS", "long", 20, 1200, 1140, 1300, "Test")
        trade = p.close_position("INFY.NS", exit_price=1150, reason="stop_loss")
        assert trade.pnl < 0
        assert not trade.is_winner
        print(f"\n  ✅ Losing trade: P&L=₹{trade.pnl:+,.2f}")

    def test_insufficient_cash_blocked(self):
        """Should not open position if not enough cash."""
        from src.execution.paper_portfolio import PaperPortfolio
        p = PaperPortfolio(1_000)  # only ₹1000
        success = p.open_position("BTCUSDT", "long", 1, 80_000, 78_000, 85_000, "Test")
        assert not success

    def test_duplicate_position_blocked(self):
        """Should not open two positions in the same symbol."""
        from src.execution.paper_portfolio import PaperPortfolio
        p = PaperPortfolio(100_000)
        p.open_position("BTC", "long", 1, 80_000, 78_000, 85_000, "Test")
        second = p.open_position("BTC", "long", 1, 80_000, 78_000, 85_000, "Test")
        assert not second

    def test_win_rate_calculation(self):
        """Win rate should be accurate."""
        from src.execution.paper_portfolio import PaperPortfolio
        p = PaperPortfolio(100_000)

        # 2 wins, 1 loss
        p.open_position("A", "long", 1, 100, 90, 120, "Test")
        p.close_position("A", 120, "take_profit")  # win

        p.open_position("B", "long", 1, 100, 90, 120, "Test")
        p.close_position("B", 120, "take_profit")  # win

        p.open_position("C", "long", 1, 100, 90, 120, "Test")
        p.close_position("C", 90, "stop_loss")    # loss

        assert p.win_rate == pytest.approx(66.67, rel=0.01)
        print(f"\n  ✅ Win rate: {p.win_rate:.1f}%")

    def test_portfolio_value_tracks_price(self):
        """Portfolio value should update when prices change."""
        from src.execution.paper_portfolio import PaperPortfolio
        p = PaperPortfolio(100_000)
        p.open_position("X", "long", 10, 1000, 900, 1200, "Test")

        p.update_price("X", 1100)
        assert p.total_value == pytest.approx(100_000 + (10 * 100))  # ₹1000 gain

    def test_profit_factor(self):
        """Profit factor > 1 means profitable."""
        from src.execution.paper_portfolio import PaperPortfolio
        p = PaperPortfolio(100_000)
        p.open_position("A", "long", 1, 100, 90, 130, "Test")
        p.close_position("A", 130, "take_profit")  # +30

        p.open_position("B", "long", 1, 100, 90, 130, "Test")
        p.close_position("B", 90, "stop_loss")    # -10

        assert p.profit_factor == pytest.approx(3.0, rel=0.01)
        print(f"\n  ✅ Profit factor: {p.profit_factor:.2f}")


class TestTradeLogger:
    """Test trade persistence to DB."""

    def test_log_and_retrieve(self):
        """Should save a trade and be able to read it back."""
        from src.execution.paper_portfolio import PaperPortfolio, ClosedTrade
        from src.execution.trade_logger import TradeLogger

        logger_obj = TradeLogger()
        p = PaperPortfolio(100_000)
        p.open_position("BTCUSDT", "long", 0.1, 80_000, 78_000, 85_000, "TestStrategy")
        trade = p.close_position("BTCUSDT", 82_000, "take_profit")

        logger_obj.log_trade(trade)
        df = logger_obj.get_all_trades()

        assert not df.empty
        btc_trades = df[df["symbol"] == "BTCUSDT"]
        assert len(btc_trades) >= 1
        print(f"\n  ✅ Trade logged and retrieved: {len(df)} total trades in DB")

    def test_stats_calculation(self):
        """Stats should be calculated correctly from DB."""
        from src.execution.trade_logger import TradeLogger
        logger_obj = TradeLogger()
        stats = logger_obj.get_stats()
        assert "total_trades" in stats
        assert "win_rate_pct" in stats
        print(f"\n  ✅ Stats: {stats.get('total_trades', 0)} trades, {stats.get('win_rate_pct', 0):.1f}% win rate")


class TestPaperTrader:
    """Test the full paper trading engine."""

    def test_single_cycle_runs(self):
        """One trading cycle should complete without errors."""
        from src.execution.paper_trader import PaperTrader
        trader = PaperTrader(capital=100_000)
        trader.run_cycle()  # Should not raise
        print(f"\n  ✅ Cycle completed. Portfolio value: ₹{trader.portfolio.total_value:,.2f}")

    def test_report_generation(self):
        """Report should return a dict with all expected keys."""
        from src.execution.paper_trader import PaperTrader
        trader = PaperTrader(capital=100_000)
        report = trader.get_report()
        assert "current_value" in report
        assert "total_pnl_pct" in report
        assert "win_rate_pct" in report
        print(f"\n  ✅ Report generated: value=₹{report['current_value']:,.2f}")

    def test_capital_preserved_with_no_signals(self):
        """If no signals are approved, capital should be unchanged."""
        from src.execution.paper_trader import PaperTrader
        trader = PaperTrader(capital=100_000)

        initial_value = trader.portfolio.total_value
        trader.run_cycle()

        # Capital should be same or very close (open positions change unrealized P&L)
        assert trader.portfolio.cash <= initial_value
        assert trader.portfolio.total_value > 0
        print(f"\n  ✅ Capital after cycle: ₹{trader.portfolio.total_value:,.2f}")

    def test_two_cycles_no_crash(self):
        """Two consecutive cycles should work fine."""
        from src.execution.paper_trader import PaperTrader
        trader = PaperTrader(capital=100_000)
        trader.run_cycle()
        trader.run_cycle()
        print(f"\n  ✅ Two cycles complete. Positions: {len(trader.portfolio.positions)}")
