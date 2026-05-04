"""
src/risk/manager.py
────────────────────
Unified Risk Manager.
Single entry point for ALL risk decisions.

Before any trade: call evaluate_signal() to get approved position size + stop levels
After any trade closes: call record_closed_trade() to update circuit breaker

Usage:
    from src.risk.manager import RiskManager
    from src.strategy.signals import Signal, Action

    risk = RiskManager(capital=100_000)

    # Evaluate a signal
    decision = risk.evaluate_signal(signal, open_positions=1, total_exposure=20000)

    if decision.approved:
        print(f"Trade approved! Buy {decision.quantity} units")
        print(f"Stop loss: ₹{decision.stop_loss}")
        print(f"Take profit: ₹{decision.take_profit}")
    else:
        print(f"Trade rejected: {decision.rejection_reason}")
"""

from dataclasses import dataclass
from src.risk.position_sizer import PositionSizer, PositionSize
from src.risk.stop_loss import StopLossManager, StopType
from src.risk.circuit_breaker import CircuitBreaker
from src.strategy.signals import Signal, Action
from src.utils.logger import logger
from config.settings import settings


@dataclass
class TradeDecision:
    """
    Result of risk evaluation for a signal.
    If approved=True, all fields are populated and the trade can be placed.
    If approved=False, check rejection_reason.
    """
    signal           : Signal
    approved         : bool
    rejection_reason : str    = ""
    quantity         : float  = 0.0
    position_value   : float  = 0.0
    stop_loss        : float  = 0.0
    take_profit      : float  = 0.0
    risk_amount      : float  = 0.0
    risk_pct         : float  = 0.0

    def __str__(self):
        if not self.approved:
            return f"❌ REJECTED [{self.signal.symbol}]: {self.rejection_reason}"
        return (
            f"✅ APPROVED [{self.signal.symbol}] "
            f"qty={self.quantity} @ ₹{self.signal.price:,.2f} "
            f"SL=₹{self.stop_loss:,.2f} TP=₹{self.take_profit:,.2f} "
            f"risk=₹{self.risk_amount:,.2f} ({self.risk_pct:.1f}%)"
        )


class RiskManager:
    """
    Master risk manager — combines position sizing, stop loss, and circuit breaker.
    This is the gatekeeper between strategy signals and actual trade execution.
    """

    def __init__(self, capital: float = None):
        self.capital        = capital or 100_000
        self.sizer          = PositionSizer()
        self.stop_manager   = StopLossManager()
        self.breaker        = CircuitBreaker(starting_capital=self.capital)

    # ── Main decision point ───────────────────────────────────────

    def evaluate_signal(
        self,
        signal          : Signal,
        open_positions  : int   = 0,
        total_exposure  : float = 0.0,
    ) -> TradeDecision:
        """
        Evaluate a strategy signal and decide if/how to trade it.

        This is the most important method — it combines:
          - Circuit breaker check (is trading allowed at all?)
          - Stop loss calculation (where do we exit if wrong?)
          - Position sizing (how much do we buy?)

        Args:
            signal        : Signal from the strategy engine
            open_positions: number of currently open positions
            total_exposure: total ₹ value of all open positions

        Returns:
            TradeDecision with approval status and trade details
        """

        # ── Step 1: Only act on BUY/SELL signals with enough confidence ──
        if signal.action == Action.HOLD:
            return TradeDecision(
                signal=signal, approved=False,
                rejection_reason="Signal is HOLD — no trade needed"
            )

        min_confidence = 0.40
        if signal.confidence < min_confidence:
            return TradeDecision(
                signal=signal, approved=False,
                rejection_reason=f"Confidence too low: {signal.confidence:.0%} (min {min_confidence:.0%})"
            )

        # ── Step 2: Calculate stop loss ───────────────────────────
        stop_loss, take_profit = self._calculate_levels(signal)

        if stop_loss is None:
            return TradeDecision(
                signal=signal, approved=False,
                rejection_reason="Cannot calculate stop loss — skipping trade"
            )

        # ── Step 3: Calculate position size ──────────────────────
        try:
            position = self.sizer.calculate(
                symbol=signal.symbol,
                entry_price=signal.price,
                stop_loss=stop_loss,
                capital=self.capital,
                confidence=signal.confidence,
            )
        except Exception as e:
            return TradeDecision(
                signal=signal, approved=False,
                rejection_reason=f"Position sizing failed: {e}"
            )

        # ── Step 4: Circuit breaker check ────────────────────────
        allowed, reason = self.breaker.check_trade_allowed(
            open_positions=open_positions,
            new_position_value=position.position_value,
            total_exposure=total_exposure,
        )

        if not allowed:
            return TradeDecision(
                signal=signal, approved=False,
                rejection_reason=reason
            )

        # ── Step 5: Approved! ────────────────────────────────────
        decision = TradeDecision(
            signal=signal,
            approved=True,
            quantity=position.quantity,
            position_value=position.position_value,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_amount=position.risk_amount,
            risk_pct=position.risk_pct,
        )

        logger.success(str(decision))
        return decision

    def record_closed_trade(self, pnl: float, capital: float):
        """Call after a trade closes to update circuit breaker stats."""
        self.capital = capital
        self.breaker.record_trade(pnl=pnl, capital=capital)

    def update_capital(self, capital: float):
        """Update available capital (e.g. after deposits or withdrawals)."""
        self.capital = capital
        self.breaker._current_capital = capital

    def get_risk_report(self) -> dict:
        """Full risk status report — good for dashboard display."""
        return {
            "capital":          round(self.capital, 2),
            "circuit_breaker":  self.breaker.get_status_report(),
            "open_stops":       self.stop_manager.get_all_positions(),
            "max_risk_per_trade_pct": settings.risk.max_position_size_pct,
            "max_daily_loss_pct":     settings.risk.max_daily_loss_pct,
            "max_open_positions":     settings.risk.max_open_positions,
        }

    # ── Private ───────────────────────────────────────────────────

    def _calculate_levels(self, signal: Signal) -> tuple[float, float]:
        """
        Determine stop loss and take profit for a signal.
        Uses signal's suggested levels if available, otherwise calculates from ATR.
        """
        stop_loss   = signal.stop_loss
        take_profit = signal.take_profit
        price       = signal.price

        # If strategy already calculated these, use them
        if stop_loss and take_profit:
            return stop_loss, take_profit

        # Fallback: use a fixed % if no ATR-based levels available
        if signal.action == Action.BUY:
            stop_loss   = round(price * 0.97, 2)   # 3% below entry
            take_profit = round(price * 1.045, 2)  # 4.5% above entry (1.5:1 R:R)
        elif signal.action == Action.SELL:
            stop_loss   = round(price * 1.03, 2)   # 3% above entry
            take_profit = round(price * 0.955, 2)  # 4.5% below entry

        return stop_loss, take_profit
