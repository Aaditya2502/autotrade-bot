"""
src/risk/stop_loss.py
──────────────────────
Stop loss and take profit engine.
Monitors open positions and triggers exits when levels are hit.

Three types of stop loss supported:
  1. Fixed    — exits at a fixed price (e.g. buy ₹1500, SL at ₹1440)
  2. ATR-based— SL = entry ± (ATR × multiplier) — adapts to volatility
  3. Trailing — SL moves UP as price rises, never moves down (locks in profit)

Take profit:
  - Fixed target price
  - Risk:Reward ratio (e.g. 2:1 means TP is 2× the distance of SL from entry)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from src.utils.logger import logger


class StopType(str, Enum):
    FIXED    = "fixed"
    ATR      = "atr"
    TRAILING = "trailing"


class ExitReason(str, Enum):
    STOP_LOSS   = "stop_loss"
    TAKE_PROFIT = "take_profit"
    MANUAL      = "manual"
    TIME_EXIT   = "time_exit"


@dataclass
class StopLossConfig:
    """Configuration for a single position's stop loss."""
    symbol        : str
    entry_price   : float
    direction     : str           # "long" or "short"
    stop_price    : float
    take_profit   : float = None
    stop_type     : StopType = StopType.FIXED
    trail_pct     : float = 2.0   # for trailing: trail by X%
    highest_price : float = 0.0   # for trailing: tracks peak price
    created_at    : datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price


@dataclass
class ExitSignal:
    """Triggered when a stop or target is hit."""
    symbol      : str
    exit_price  : float
    reason      : ExitReason
    pnl_pct     : float    # % profit/loss
    message     : str


class StopLossManager:
    """
    Manages stop losses and take profits for all open positions.
    Call check_exits() on every new price update.
    """

    def __init__(self):
        self._positions: dict[str, StopLossConfig] = {}

    def add_position(
        self,
        symbol      : str,
        entry_price : float,
        stop_price  : float,
        take_profit : float = None,
        direction   : str = "long",
        stop_type   : StopType = StopType.FIXED,
        trail_pct   : float = 2.0,
    ) -> StopLossConfig:
        """Register a new position for stop loss monitoring."""
        config = StopLossConfig(
            symbol=symbol,
            entry_price=entry_price,
            direction=direction,
            stop_price=stop_price,
            take_profit=take_profit,
            stop_type=stop_type,
            trail_pct=trail_pct,
        )
        self._positions[symbol] = config
        logger.info(
            f"Stop loss set: {symbol} entry=₹{entry_price:,.2f} "
            f"SL=₹{stop_price:,.2f} TP=₹{take_profit if take_profit else 'None'} "
            f"[{stop_type.value}]"
        )
        return config

    def check_exits(self, symbol: str, current_price: float) -> ExitSignal | None:
        """
        Check if current price has hit stop loss or take profit.
        Call this every time you get a new price.

        Returns:
            ExitSignal if an exit is triggered, None otherwise
        """
        if symbol not in self._positions:
            return None

        config = self._positions[symbol]

        # Update trailing stop if needed
        if config.stop_type == StopType.TRAILING:
            self._update_trailing(config, current_price)

        # Check stop loss
        if self._is_stop_hit(config, current_price):
            pnl_pct = self._calc_pnl_pct(config, current_price)
            signal = ExitSignal(
                symbol=symbol,
                exit_price=current_price,
                reason=ExitReason.STOP_LOSS,
                pnl_pct=pnl_pct,
                message=f"🛑 STOP LOSS hit: {symbol} @ ₹{current_price:,.2f} | P&L: {pnl_pct:+.2f}%"
            )
            logger.warning(signal.message)
            del self._positions[symbol]
            return signal

        # Check take profit
        if config.take_profit and self._is_tp_hit(config, current_price):
            pnl_pct = self._calc_pnl_pct(config, current_price)
            signal = ExitSignal(
                symbol=symbol,
                exit_price=current_price,
                reason=ExitReason.TAKE_PROFIT,
                pnl_pct=pnl_pct,
                message=f"✅ TAKE PROFIT hit: {symbol} @ ₹{current_price:,.2f} | P&L: {pnl_pct:+.2f}%"
            )
            logger.success(signal.message)
            del self._positions[symbol]
            return signal

        return None

    def remove_position(self, symbol: str):
        """Remove a position from monitoring (e.g. manually closed)."""
        if symbol in self._positions:
            del self._positions[symbol]
            logger.info(f"Removed stop loss monitor for {symbol}")

    def get_all_positions(self) -> dict:
        """Get all monitored positions and their current stop levels."""
        return {
            sym: {
                "entry":       cfg.entry_price,
                "stop":        cfg.stop_price,
                "take_profit": cfg.take_profit,
                "type":        cfg.stop_type.value,
            }
            for sym, cfg in self._positions.items()
        }

    # ── Private ───────────────────────────────────────────────────

    def _update_trailing(self, config: StopLossConfig, current_price: float):
        """Move trailing stop up when price rises (long positions)."""
        if config.direction == "long" and current_price > config.highest_price:
            config.highest_price = current_price
            new_stop = current_price * (1 - config.trail_pct / 100)
            if new_stop > config.stop_price:
                old_stop = config.stop_price
                config.stop_price = round(new_stop, 2)
                logger.debug(
                    f"Trailing stop updated: {config.symbol} "
                    f"₹{old_stop:,.2f} → ₹{config.stop_price:,.2f} "
                    f"(price peaked at ₹{current_price:,.2f})"
                )

    def _is_stop_hit(self, config: StopLossConfig, price: float) -> bool:
        if config.direction == "long":
            return price <= config.stop_price
        else:  # short
            return price >= config.stop_price

    def _is_tp_hit(self, config: StopLossConfig, price: float) -> bool:
        if config.direction == "long":
            return price >= config.take_profit
        else:
            return price <= config.take_profit

    def _calc_pnl_pct(self, config: StopLossConfig, exit_price: float) -> float:
        if config.direction == "long":
            return ((exit_price - config.entry_price) / config.entry_price) * 100
        else:
            return ((config.entry_price - exit_price) / config.entry_price) * 100
