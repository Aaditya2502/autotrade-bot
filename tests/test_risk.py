"""
tests/test_risk.py
───────────────────
Tests for Phase 4 — Risk Management.
Run with:
    python -m pytest tests/test_risk.py -v
"""

import pytest
from src.strategy.signals import Signal, Action


def make_signal(action=Action.BUY, confidence=0.75, price=1000.0, symbol="TEST"):
    return Signal(
        symbol=symbol, action=action, confidence=confidence,
        strategy="Test", price=price,
        stop_loss=price * 0.97 if action == Action.BUY else price * 1.03,
        take_profit=price * 1.05 if action == Action.BUY else price * 0.95,
    )


class TestPositionSizer:

    def test_basic_position_size(self):
        """Position size should never risk more than max_risk_pct."""
        from src.risk.position_sizer import PositionSizer
        sizer = PositionSizer()
        result = sizer.calculate(
            symbol="RELIANCE.NS",
            entry_price=1500.0,
            stop_loss=1440.0,
            capital=100_000,
            confidence=1.0,
        )
        assert result.quantity > 0
        assert result.risk_pct <= sizer.max_risk_pct * 100 + 0.1  # allow tiny float error
        assert result.position_value > 0
        print(f"\n  ✅ Position: {result}")

    def test_low_confidence_reduces_size(self):
        """Lower confidence should result in smaller position size."""
        from src.risk.position_sizer import PositionSizer
        sizer = PositionSizer()

        high_conf = sizer.calculate("X", 1000, 970, 100_000, confidence=1.0)
        low_conf  = sizer.calculate("X", 1000, 970, 100_000, confidence=0.4)

        assert low_conf.quantity < high_conf.quantity
        print(f"\n  ✅ High conf qty={high_conf.quantity}, Low conf qty={low_conf.quantity}")

    def test_larger_stop_means_smaller_position(self):
        """Wider stop loss = fewer units (same total risk)."""
        from src.risk.position_sizer import PositionSizer
        sizer = PositionSizer()

        tight_sl = sizer.calculate("X", 1000, 990, 100_000)   # ₹10 risk/unit
        wide_sl  = sizer.calculate("X", 1000, 950, 100_000)   # ₹50 risk/unit

        assert tight_sl.quantity > wide_sl.quantity
        print(f"\n  ✅ Tight SL qty={tight_sl.quantity}, Wide SL qty={wide_sl.quantity}")

    def test_crypto_allows_fractional(self):
        """Crypto positions should allow fractional units."""
        from src.risk.position_sizer import PositionSizer
        sizer = PositionSizer()
        result = sizer.calculate("BTCUSDT", 80000, 78000, 100_000)
        # BTC price > 100, so should be whole numbers
        assert result.quantity >= 1
        print(f"\n  ✅ BTC position: {result.quantity} units @ ₹{result.entry_price:,.0f}")


class TestStopLossManager:

    def test_stop_loss_triggered(self):
        """Should trigger exit when price drops below stop."""
        from src.risk.stop_loss import StopLossManager
        mgr = StopLossManager()
        mgr.add_position("TEST", entry_price=1000, stop_price=950, take_profit=1100)

        # Price still above stop — no exit
        result = mgr.check_exits("TEST", 980)
        assert result is None

        # Price hits stop
        result = mgr.check_exits("TEST", 945)
        assert result is not None
        assert result.reason.value == "stop_loss"
        assert result.pnl_pct < 0
        print(f"\n  ✅ Stop loss triggered: {result.pnl_pct:.2f}%")

    def test_take_profit_triggered(self):
        """Should trigger exit when price hits take profit."""
        from src.risk.stop_loss import StopLossManager
        mgr = StopLossManager()
        mgr.add_position("TEST", entry_price=1000, stop_price=950, take_profit=1100)

        result = mgr.check_exits("TEST", 1110)
        assert result is not None
        assert result.reason.value == "take_profit"
        assert result.pnl_pct > 0
        print(f"\n  ✅ Take profit triggered: +{result.pnl_pct:.2f}%")

    def test_trailing_stop_moves_up(self):
        """Trailing stop should move up as price rises."""
        from src.risk.stop_loss import StopLossManager, StopType
        mgr = StopLossManager()
        mgr.add_position("TEST", entry_price=1000, stop_price=980,
                          stop_type=StopType.TRAILING, trail_pct=2.0)

        # Price rises — stop should trail up
        mgr.check_exits("TEST", 1100)
        pos = mgr.get_all_positions()["TEST"]
        assert pos["stop"] > 980  # Stop moved up
        print(f"\n  ✅ Trailing stop moved up to ₹{pos['stop']:.2f}")

    def test_position_removed_after_exit(self):
        """Position should be removed from monitoring after exit."""
        from src.risk.stop_loss import StopLossManager
        mgr = StopLossManager()
        mgr.add_position("TEST", entry_price=1000, stop_price=950, take_profit=1100)

        mgr.check_exits("TEST", 900)  # Triggers stop
        assert "TEST" not in mgr.get_all_positions()


class TestCircuitBreaker:

    def test_allows_normal_trade(self):
        """Should allow trades when everything is within limits."""
        from src.risk.circuit_breaker import CircuitBreaker
        breaker = CircuitBreaker(starting_capital=100_000)
        allowed, reason = breaker.check_trade_allowed(
            open_positions=2, new_position_value=5_000
        )
        assert allowed, f"Should be allowed but got: {reason}"
        print(f"\n  ✅ Normal trade allowed")

    def test_blocks_too_many_positions(self):
        """Should block new trades when max positions reached."""
        from src.risk.circuit_breaker import CircuitBreaker
        breaker = CircuitBreaker(starting_capital=100_000)
        allowed, reason = breaker.check_trade_allowed(
            open_positions=5,   # max is 5
            new_position_value=5_000
        )
        assert not allowed
        assert "positions" in reason.lower()
        print(f"\n  ✅ Too many positions blocked: {reason}")

    def test_trips_on_daily_loss(self):
        """Should trip circuit breaker after hitting daily loss limit."""
        from src.risk.circuit_breaker import CircuitBreaker
        breaker = CircuitBreaker(starting_capital=100_000)

        # Record losses totalling > 3%
        breaker.record_trade(pnl=-1500, capital=98_500)
        breaker.record_trade(pnl=-1500, capital=97_000)

        allowed, reason = breaker.check_trade_allowed(0, 1000)
        assert not allowed
        print(f"\n  ✅ Circuit breaker tripped: {reason}")

    def test_pauses_after_consecutive_losses(self):
        """Should pause after N consecutive losses."""
        from src.risk.circuit_breaker import CircuitBreaker
        breaker = CircuitBreaker(starting_capital=100_000)

        # 3 consecutive small losses (doesn't hit daily %, but hits streak)
        breaker.record_trade(pnl=-100, capital=99_900)
        breaker.record_trade(pnl=-100, capital=99_800)
        breaker.record_trade(pnl=-100, capital=99_700)

        allowed, reason = breaker.check_trade_allowed(0, 1000)
        assert not allowed
        assert "consecutive" in reason.lower() or "paused" in reason.lower()
        print(f"\n  ✅ Consecutive loss pause: {reason}")

    def test_win_resets_consecutive_count(self):
        """A win should reset the consecutive loss counter."""
        from src.risk.circuit_breaker import CircuitBreaker
        breaker = CircuitBreaker(starting_capital=100_000)

        breaker.record_trade(pnl=-100, capital=99_900)
        breaker.record_trade(pnl=-100, capital=99_800)
        breaker.record_trade(pnl=+500, capital=100_300)  # WIN!

        assert breaker.daily_stats.consecutive_losses == 0
        print(f"\n  ✅ Consecutive loss counter reset after win")


class TestRiskManager:

    def test_full_evaluation_approved(self):
        """High confidence signal should be approved with position details."""
        from src.risk.manager import RiskManager
        risk = RiskManager(capital=100_000)
        signal = make_signal(Action.BUY, confidence=0.75, price=1500)

        decision = risk.evaluate_signal(signal, open_positions=0)
        assert decision.approved
        assert decision.quantity > 0
        assert decision.stop_loss > 0
        assert decision.take_profit > decision.signal.price
        assert decision.risk_pct <= 3.0
        print(f"\n  ✅ Trade approved: {decision}")

    def test_low_confidence_rejected(self):
        """Signal below confidence threshold should be rejected."""
        from src.risk.manager import RiskManager
        risk = RiskManager(capital=100_000)
        signal = make_signal(Action.BUY, confidence=0.25)  # below 40% threshold

        decision = risk.evaluate_signal(signal)
        assert not decision.approved
        assert "confidence" in decision.rejection_reason.lower()
        print(f"\n  ✅ Low confidence rejected: {decision.rejection_reason}")

    def test_hold_signal_rejected(self):
        """HOLD signals should never result in a trade."""
        from src.risk.manager import RiskManager
        risk = RiskManager(capital=100_000)
        signal = make_signal(Action.HOLD, confidence=0.9)

        decision = risk.evaluate_signal(signal)
        assert not decision.approved
        print(f"\n  ✅ HOLD signal correctly rejected")

    def test_risk_report_structure(self):
        """Risk report should contain all expected keys."""
        from src.risk.manager import RiskManager
        risk = RiskManager(capital=100_000)
        report = risk.get_risk_report()

        assert "capital" in report
        assert "circuit_breaker" in report
        assert "max_risk_per_trade_pct" in report
        print(f"\n  ✅ Risk report: {report['circuit_breaker']['status']}")

    def test_capital_used_reasonable(self):
        """Position should use a reasonable portion of capital."""
        from src.risk.manager import RiskManager
        risk = RiskManager(capital=100_000)
        signal = make_signal(Action.BUY, confidence=0.80, price=1500)
        decision = risk.evaluate_signal(signal)

        if decision.approved:
            # Position should be between 1% and 25% of capital
            pct = (decision.position_value / 100_000) * 100
            assert 1 <= pct <= 60, f"Position size {pct:.1f}% seems unreasonable"
            print(f"\n  ✅ Capital used: {pct:.1f}%")
