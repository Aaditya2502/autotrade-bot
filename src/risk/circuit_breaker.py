"""
src/risk/circuit_breaker.py
────────────────────────────
Circuit breaker — the bot's emergency stop system.

Rules:
  1. Daily loss limit    — halt all trading if daily loss > X% of capital
  2. Max open positions  — reject new trades if too many positions open
  3. Max exposure        — reject if total position value > X% of capital
  4. Consecutive losses  — pause after N losses in a row

Think of this as the fuse box for your trading bot.
If something goes wrong, it trips and nothing else trades until you manually reset.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from config.settings import settings
from src.utils.logger import logger


class BreakerStatus(str, Enum):
    OK      = "ok"       # All clear, trading allowed
    TRIPPED = "tripped"  # Circuit breaker triggered, no trading
    PAUSED  = "paused"   # Temporarily paused, will resume


@dataclass
class DailyStats:
    """Tracks trading stats for the current day."""
    date            : date  = field(default_factory=date.today)
    starting_capital: float = 0.0
    realized_pnl    : float = 0.0   # Closed trade P&L today
    trades_taken    : int   = 0
    winning_trades  : int   = 0
    losing_trades   : int   = 0
    consecutive_losses: int = 0
    max_loss_pct    : float = 0.0   # Worst single trade today

    @property
    def loss_pct(self) -> float:
        """How much of starting capital lost today (as %)."""
        if self.starting_capital == 0:
            return 0.0
        return -(self.realized_pnl / self.starting_capital) * 100

    @property
    def win_rate(self) -> float:
        if self.trades_taken == 0:
            return 0.0
        return (self.winning_trades / self.trades_taken) * 100


class CircuitBreaker:
    """
    Monitors trading activity and halts the bot if risk limits are exceeded.

    Usage:
        breaker = CircuitBreaker(starting_capital=100_000)

        # Before placing any trade:
        allowed, reason = breaker.check_trade_allowed(open_positions=2, new_position_value=5000)
        if not allowed:
            print(f"Trade blocked: {reason}")
            return

        # After each trade closes:
        breaker.record_trade(pnl=−1500, capital=98_500)
    """

    def __init__(self, starting_capital: float = 100_000):
        self.max_daily_loss_pct   = settings.risk.max_daily_loss_pct        # e.g. 3.0
        self.max_open_positions   = settings.risk.max_open_positions         # e.g. 5
        self.max_position_size_pct= settings.risk.max_position_size_pct     # e.g. 2.0
        self.max_consecutive_losses = 3       # Pause after 3 losses in a row
        self.max_exposure_pct     = 60.0      # Never have >60% of capital in open positions

        self.status = BreakerStatus.OK
        self.trip_reason = ""
        self.daily_stats = DailyStats(starting_capital=starting_capital)
        self._current_capital = starting_capital

    # ── Main check — call before every trade ─────────────────────

    def check_trade_allowed(
        self,
        open_positions    : int,
        new_position_value: float,
        total_exposure    : float = 0.0,
    ) -> tuple[bool, str]:
        """
        Check if a new trade is allowed.

        Args:
            open_positions    : number of currently open positions
            new_position_value: ₹ value of the trade being considered
            total_exposure    : total ₹ value of all open positions

        Returns:
            (True, "") if allowed
            (False, reason) if blocked
        """
        self._refresh_daily_stats()

        # 1. Circuit breaker already tripped
        if self.status == BreakerStatus.TRIPPED:
            return False, f"🚨 Circuit breaker TRIPPED: {self.trip_reason}"

        if self.status == BreakerStatus.PAUSED:
            return False, f"⏸️ Trading PAUSED: {self.trip_reason}"

        # 2. Daily loss limit
        if self.daily_stats.loss_pct >= self.max_daily_loss_pct:
            self._trip(f"Daily loss limit reached: -{self.daily_stats.loss_pct:.1f}% (max: -{self.max_daily_loss_pct}%)")
            return False, self.trip_reason

        # 3. Too many open positions
        if open_positions >= self.max_open_positions:
            return False, f"Max open positions reached ({open_positions}/{self.max_open_positions})"

        # 4. Position too large
        position_pct = (new_position_value / self._current_capital) * 100
        if position_pct > 60:  # No single position > 60% of capital
            return False, f"Position too large: {position_pct:.1f}% of capital (max 60%)"

        # 5. Total exposure too high
        total_exposure_pct = ((total_exposure + new_position_value) / self._current_capital) * 100
        if total_exposure_pct > self.max_exposure_pct:
            return False, f"Total exposure too high: {total_exposure_pct:.1f}% (max {self.max_exposure_pct}%)"

        # 6. Too many consecutive losses — pause, not hard stop
        if self.daily_stats.consecutive_losses >= self.max_consecutive_losses:
            self._pause(f"{self.daily_stats.consecutive_losses} consecutive losses — taking a break")
            return False, self.trip_reason

        return True, ""

    def record_trade(self, pnl: float, capital: float):
        """
        Call after each trade closes.

        Args:
            pnl    : profit/loss in ₹ (negative = loss)
            capital: current total capital after this trade
        """
        self._current_capital = capital
        self.daily_stats.realized_pnl += pnl
        self.daily_stats.trades_taken += 1

        if pnl > 0:
            self.daily_stats.winning_trades += 1
            self.daily_stats.consecutive_losses = 0  # Reset streak
            logger.success(f"Trade closed: +₹{pnl:,.2f} | Daily P&L: {self.daily_stats.realized_pnl:+,.2f}")
        else:
            self.daily_stats.losing_trades += 1
            self.daily_stats.consecutive_losses += 1
            loss_pct = abs(pnl / capital * 100)
            self.daily_stats.max_loss_pct = max(self.daily_stats.max_loss_pct, loss_pct)
            logger.warning(
                f"Trade closed: -₹{abs(pnl):,.2f} | "
                f"Consecutive losses: {self.daily_stats.consecutive_losses} | "
                f"Daily loss: -{self.daily_stats.loss_pct:.2f}%"
            )

        # Re-check after recording
        if self.daily_stats.loss_pct >= self.max_daily_loss_pct:
            self._trip(f"Daily loss limit hit: -{self.daily_stats.loss_pct:.1f}%")

    def reset_pause(self):
        """Manually resume after a pause (e.g. operator confirms to continue)."""
        if self.status == BreakerStatus.PAUSED:
            self.status = BreakerStatus.OK
            self.trip_reason = ""
            self.daily_stats.consecutive_losses = 0
            logger.info("Circuit breaker PAUSE reset — trading resumed")

    def manual_reset(self):
        """Hard reset — use only after investigating why it tripped."""
        self.status = BreakerStatus.OK
        self.trip_reason = ""
        logger.warning("Circuit breaker MANUALLY RESET — make sure you know why it tripped!")

    def get_status_report(self) -> dict:
        """Get a summary of current risk status."""
        return {
            "status":             self.status.value,
            "trip_reason":        self.trip_reason,
            "daily_loss_pct":     round(self.daily_stats.loss_pct, 2),
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "trades_today":       self.daily_stats.trades_taken,
            "win_rate_today":     round(self.daily_stats.win_rate, 1),
            "consecutive_losses": self.daily_stats.consecutive_losses,
            "realized_pnl_today": round(self.daily_stats.realized_pnl, 2),
            "current_capital":    round(self._current_capital, 2),
        }

    # ── Private ───────────────────────────────────────────────────

    def _trip(self, reason: str):
        self.status = BreakerStatus.TRIPPED
        self.trip_reason = reason
        logger.error(f"🚨 CIRCUIT BREAKER TRIPPED: {reason}")
        logger.error("All trading halted. Manual reset required.")

    def _pause(self, reason: str):
        self.status = BreakerStatus.PAUSED
        self.trip_reason = reason
        logger.warning(f"⏸️ Trading PAUSED: {reason}")

    def _refresh_daily_stats(self):
        """Reset daily stats at midnight."""
        if self.daily_stats.date != date.today():
            logger.info("New trading day — resetting daily stats and circuit breaker")
            self.daily_stats = DailyStats(starting_capital=self._current_capital)
            if self.status == BreakerStatus.TRIPPED:
                self.status = BreakerStatus.OK
                self.trip_reason = ""
