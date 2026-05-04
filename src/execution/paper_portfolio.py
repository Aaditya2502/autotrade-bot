"""
src/execution/paper_portfolio.py
──────────────────────────────────
Virtual portfolio for paper trading.
Tracks simulated positions, cash balance, and P&L
exactly as if you were trading real money.

No real money ever moves. This is purely accounting.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from src.utils.logger import logger


@dataclass
class Position:
    """A single open position in the paper portfolio."""
    symbol      : str
    side        : str           # "long" or "short"
    quantity    : float
    entry_price : float
    stop_loss   : float
    take_profit : float
    strategy    : str
    opened_at   : datetime = field(default_factory=datetime.now)
    current_price: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        if not self.current_price:
            return 0.0
        if self.side == "long":
            return (self.current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - self.current_price) * self.quantity

    @property
    def unrealized_pnl_pct(self) -> float:
        if not self.current_price or self.entry_price == 0:
            return 0.0
        if self.side == "long":
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100

    @property
    def position_value(self) -> float:
        return self.quantity * (self.current_price or self.entry_price)


@dataclass
class ClosedTrade:
    """A completed trade with final P&L."""
    symbol      : str
    side        : str
    quantity    : float
    entry_price : float
    exit_price  : float
    stop_loss   : float
    take_profit : float
    strategy    : str
    exit_reason : str
    opened_at   : datetime
    closed_at   : datetime = field(default_factory=datetime.now)

    @property
    def pnl(self) -> float:
        if self.side == "long":
            return (self.exit_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - self.exit_price) * self.quantity

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.side == "long":
            return ((self.exit_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.exit_price) / self.entry_price) * 100

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0


class PaperPortfolio:
    """
    Simulated portfolio for paper trading.
    Tracks cash, open positions, and closed trade history.
    """

    def __init__(self, starting_capital: float = 100_000):
        self.starting_capital = starting_capital
        self.cash             = starting_capital
        self.positions        : dict[str, Position] = {}
        self.closed_trades    : list[ClosedTrade]   = []
        logger.info(f"Paper portfolio initialised with ₹{starting_capital:,.0f}")

    # ── Trade execution ───────────────────────────────────────────

    def open_position(
        self,
        symbol      : str,
        side        : str,
        quantity    : float,
        price       : float,
        stop_loss   : float,
        take_profit : float,
        strategy    : str,
    ) -> bool:
        """
        Open a new paper position.
        Returns True if successful, False if insufficient cash.
        """
        cost = quantity * price

        if cost > self.cash:
            logger.warning(f"Insufficient cash: need ₹{cost:,.2f}, have ₹{self.cash:,.2f}")
            return False

        if symbol in self.positions:
            logger.warning(f"Already have an open position in {symbol} — skipping")
            return False

        self.cash -= cost
        self.positions[symbol] = Position(
            symbol=symbol, side=side, quantity=quantity,
            entry_price=price, stop_loss=stop_loss,
            take_profit=take_profit, strategy=strategy,
            current_price=price,
        )

        icon = "🟢" if side == "long" else "🔴"
        logger.success(
            f"{icon} PAPER TRADE OPENED: {side.upper()} {quantity} × {symbol} "
            f"@ ₹{price:,.2f} | SL=₹{stop_loss:,.2f} TP=₹{take_profit:,.2f} "
            f"| Cash remaining: ₹{self.cash:,.2f}"
        )
        return True

    def close_position(
        self,
        symbol      : str,
        exit_price  : float,
        reason      : str = "manual",
    ) -> Optional[ClosedTrade]:
        """
        Close an open position and record the trade.
        Returns the ClosedTrade or None if no position found.
        """
        if symbol not in self.positions:
            logger.warning(f"No open position found for {symbol}")
            return None

        pos = self.positions.pop(symbol)
        proceeds = pos.quantity * exit_price
        self.cash += proceeds

        trade = ClosedTrade(
            symbol=symbol, side=pos.side,
            quantity=pos.quantity,
            entry_price=pos.entry_price, exit_price=exit_price,
            stop_loss=pos.stop_loss, take_profit=pos.take_profit,
            strategy=pos.strategy, exit_reason=reason,
            opened_at=pos.opened_at,
        )
        self.closed_trades.append(trade)

        icon = "✅" if trade.is_winner else "❌"
        logger.info(
            f"{icon} PAPER TRADE CLOSED: {symbol} @ ₹{exit_price:,.2f} "
            f"| P&L: ₹{trade.pnl:+,.2f} ({trade.pnl_pct:+.2f}%) "
            f"| Reason: {reason} | Cash: ₹{self.cash:,.2f}"
        )
        return trade

    def update_price(self, symbol: str, price: float):
        """Update current price for an open position."""
        if symbol in self.positions:
            self.positions[symbol].current_price = price

    # ── Portfolio metrics ─────────────────────────────────────────

    @property
    def total_value(self) -> float:
        """Cash + value of all open positions at current prices."""
        open_value = sum(p.position_value for p in self.positions.values())
        return self.cash + open_value

    @property
    def total_pnl(self) -> float:
        """Total P&L = current value - starting capital."""
        return self.total_value - self.starting_capital

    @property
    def total_pnl_pct(self) -> float:
        return (self.total_pnl / self.starting_capital) * 100

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def realized_pnl(self) -> float:
        return sum(t.pnl for t in self.closed_trades)

    @property
    def win_rate(self) -> float:
        if not self.closed_trades:
            return 0.0
        winners = sum(1 for t in self.closed_trades if t.is_winner)
        return (winners / len(self.closed_trades)) * 100

    @property
    def avg_win(self) -> float:
        wins = [t.pnl for t in self.closed_trades if t.is_winner]
        return sum(wins) / len(wins) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [t.pnl for t in self.closed_trades if not t.is_winner]
        return sum(losses) / len(losses) if losses else 0.0

    @property
    def profit_factor(self) -> float:
        """Total wins / Total losses (>1 = profitable system)."""
        total_win  = sum(t.pnl for t in self.closed_trades if t.is_winner)
        total_loss = abs(sum(t.pnl for t in self.closed_trades if not t.is_winner))
        return total_win / total_loss if total_loss > 0 else float('inf')

    def get_summary(self) -> dict:
        """Full portfolio summary."""
        return {
            "starting_capital" : self.starting_capital,
            "current_value"    : round(self.total_value, 2),
            "cash"             : round(self.cash, 2),
            "total_pnl"        : round(self.total_pnl, 2),
            "total_pnl_pct"    : round(self.total_pnl_pct, 2),
            "realized_pnl"     : round(self.realized_pnl, 2),
            "unrealized_pnl"   : round(self.unrealized_pnl, 2),
            "open_positions"   : len(self.positions),
            "closed_trades"    : len(self.closed_trades),
            "win_rate_pct"     : round(self.win_rate, 1),
            "avg_win"          : round(self.avg_win, 2),
            "avg_loss"         : round(self.avg_loss, 2),
            "profit_factor"    : round(self.profit_factor, 3),
        }
