"""
tests/test_dashboard.py
────────────────────────
Tests for Phase 6 — Dashboard & Alerts.
Run with:
    python -m pytest tests/test_dashboard.py -v
"""

import pytest


class TestTelegramAlert:
    """Test Telegram alert system."""

    def test_init_without_credentials(self):
        """Should init gracefully even without Telegram credentials."""
        from src.alerts.telegram_bot import TelegramAlert
        alert = TelegramAlert()
        # Should not raise — just sets enabled=False
        assert hasattr(alert, "enabled")

    def test_send_disabled_returns_false(self):
        """When disabled, send should return False silently."""
        from src.alerts.telegram_bot import TelegramAlert
        alert = TelegramAlert()
        if not alert.enabled:
            result = alert.send("Test message")
            assert result == False
            print("\n  ✅ Telegram correctly disabled (no credentials)")

    def test_trade_opened_message_format(self):
        """Trade opened message should be formatted correctly."""
        from src.alerts.telegram_bot import TelegramAlert
        alert = TelegramAlert()
        # Even disabled, the method should run without error
        alert.trade_opened("BTCUSDT", "long", 0.1, 80000, 78000, 85000, "EMA_Crossover")
        print("\n  ✅ trade_opened message formatted without error")

    def test_trade_closed_message_format(self):
        """Trade closed message should be formatted correctly."""
        from src.alerts.telegram_bot import TelegramAlert
        alert = TelegramAlert()
        alert.trade_closed("RELIANCE.NS", 1500, 500, 2.5, "take_profit")
        print("\n  ✅ trade_closed message formatted without error")

    def test_circuit_breaker_message(self):
        """Circuit breaker alert should format correctly."""
        from src.alerts.telegram_bot import TelegramAlert
        alert = TelegramAlert()
        alert.circuit_breaker_tripped("Daily loss limit reached: -3.1%")
        print("\n  ✅ circuit_breaker message formatted without error")

    def test_daily_summary_message(self):
        """Daily summary should format correctly."""
        from src.alerts.telegram_bot import TelegramAlert
        alert = TelegramAlert()
        alert.daily_summary(
            portfolio_value=102_000,
            pnl=2_000,
            pnl_pct=2.0,
            trades=5,
            win_rate=60.0,
        )
        print("\n  ✅ daily_summary message formatted without error")


class TestDashboardImports:
    """Test that dashboard can be imported without errors."""

    def test_dashboard_imports(self):
        """All dashboard dependencies should import cleanly."""
        try:
            import streamlit
            import plotly
            print("\n  ✅ streamlit and plotly available")
        except ImportError as e:
            pytest.skip(f"Dashboard deps not installed: {e}")

    def test_trade_logger_for_dashboard(self):
        """Trade logger should work for dashboard display."""
        from src.execution.trade_logger import TradeLogger
        tl = TradeLogger()
        df = tl.get_all_trades()
        stats = tl.get_stats()
        assert isinstance(stats, dict)
        assert "total_trades" in stats
        print(f"\n  ✅ Trade logger: {stats['total_trades']} trades in DB")

    def test_paper_trader_report(self):
        """Paper trader report should generate cleanly."""
        from src.execution.paper_trader import PaperTrader
        trader = PaperTrader(capital=100_000)
        summary = trader.portfolio.get_summary()
        assert "current_value" in summary
        assert "win_rate_pct" in summary
        print(f"\n  ✅ Portfolio summary: ₹{summary['current_value']:,.0f}")

    def test_risk_report_for_dashboard(self):
        """Risk report should have all keys dashboard needs."""
        from src.risk.manager import RiskManager
        risk = RiskManager(capital=100_000)
        report = risk.get_risk_report()
        cb = report["circuit_breaker"]
        assert "status" in cb
        assert "daily_loss_pct" in cb
        assert "trades_today" in cb
        print(f"\n  ✅ Risk report: status={cb['status']}")
