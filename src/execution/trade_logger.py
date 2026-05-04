"""
src/execution/trade_logger.py
───────────────────────────────
Persists paper trade history to the SQLite database.
Survives restarts — you can always replay what the bot did.
"""

import pandas as pd
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Integer, Boolean
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.data.database import Base, engine, get_session, init_db
from src.execution.paper_portfolio import ClosedTrade
from src.utils.logger import logger


class TradeRecord(Base):
    """DB model for a single completed trade."""
    __tablename__ = "paper_trades"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    symbol      = Column(String(20),  nullable=False)
    side        = Column(String(10),  nullable=False)   # long | short
    quantity    = Column(Float,       nullable=False)
    entry_price = Column(Float,       nullable=False)
    exit_price  = Column(Float,       nullable=False)
    stop_loss   = Column(Float,       nullable=True)
    take_profit = Column(Float,       nullable=True)
    pnl         = Column(Float,       nullable=False)
    pnl_pct     = Column(Float,       nullable=False)
    is_winner   = Column(Boolean,     nullable=False)
    strategy    = Column(String(50),  nullable=True)
    exit_reason = Column(String(50),  nullable=True)
    opened_at   = Column(DateTime,    nullable=False)
    closed_at   = Column(DateTime,    nullable=False)


class TradeLogger:
    """Saves and loads paper trade history from the database."""

    def __init__(self):
        init_db()
        # Create paper_trades table if it doesn't exist
        Base.metadata.create_all(bind=engine)

    def log_trade(self, trade: ClosedTrade):
        """Save a closed trade to the database."""
        with get_session() as session:
            stmt = sqlite_insert(TradeRecord).values(
                symbol      = trade.symbol,
                side        = trade.side,
                quantity    = trade.quantity,
                entry_price = trade.entry_price,
                exit_price  = trade.exit_price,
                stop_loss   = trade.stop_loss,
                take_profit = trade.take_profit,
                pnl         = round(trade.pnl, 2),
                pnl_pct     = round(trade.pnl_pct, 2),
                is_winner   = trade.is_winner,
                strategy    = trade.strategy,
                exit_reason = trade.exit_reason,
                opened_at   = trade.opened_at,
                closed_at   = trade.closed_at or datetime.now(),
            ).on_conflict_do_nothing()
            session.execute(stmt)
            session.commit()
        logger.debug(f"Trade logged to DB: {trade.symbol} P&L={trade.pnl:+.2f}")

    def get_all_trades(self) -> pd.DataFrame:
        """Load all paper trades from DB as a DataFrame."""
        with get_session() as session:
            rows = session.query(TradeRecord).order_by(TradeRecord.closed_at.desc()).all()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame([{
            "symbol"     : r.symbol,
            "side"       : r.side,
            "quantity"   : r.quantity,
            "entry"      : r.entry_price,
            "exit"       : r.exit_price,
            "pnl"        : r.pnl,
            "pnl_pct"    : r.pnl_pct,
            "winner"     : r.is_winner,
            "strategy"   : r.strategy,
            "exit_reason": r.exit_reason,
            "opened_at"  : r.opened_at,
            "closed_at"  : r.closed_at,
        } for r in rows])

    def get_stats(self) -> dict:
        """Quick summary stats from trade history."""
        df = self.get_all_trades()
        if df.empty:
            return {"total_trades": 0}

        return {
            "total_trades"   : len(df),
            "winning_trades" : int(df["winner"].sum()),
            "losing_trades"  : int((~df["winner"]).sum()),
            "win_rate_pct"   : round(df["winner"].mean() * 100, 1),
            "total_pnl"      : round(df["pnl"].sum(), 2),
            "avg_pnl"        : round(df["pnl"].mean(), 2),
            "best_trade"     : round(df["pnl"].max(), 2),
            "worst_trade"    : round(df["pnl"].min(), 2),
            "avg_win"        : round(df[df["winner"]]["pnl"].mean(), 2) if df["winner"].any() else 0,
            "avg_loss"       : round(df[~df["winner"]]["pnl"].mean(), 2) if (~df["winner"]).any() else 0,
        }
