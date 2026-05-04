"""
src/data/database.py
─────────────────────
Database models and setup using SQLAlchemy.
Stores all OHLCV candles in a local SQLite file.

Tables:
  - candles     : OHLCV data for all symbols + timeframes
  - fetch_log   : Tracks when each symbol was last fetched
"""

from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Float,
    DateTime, Integer, UniqueConstraint, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from config.settings import settings
from src.utils.logger import logger

Base = declarative_base()


# ── Models ────────────────────────────────────────────────────────

class Candle(Base):
    """One OHLCV row for a symbol at a given timeframe."""
    __tablename__ = "candles"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    symbol    = Column(String(20),  nullable=False)   # e.g. "RELIANCE.NS", "BTCUSDT"
    exchange  = Column(String(20),  nullable=False)   # "NSE", "BSE", "BINANCE"
    timeframe = Column(String(10),  nullable=False)   # "1d", "1h", "15m" etc.
    timestamp = Column(DateTime,    nullable=False)
    open      = Column(Float,       nullable=False)
    high      = Column(Float,       nullable=False)
    low       = Column(Float,       nullable=False)
    close     = Column(Float,       nullable=False)
    volume    = Column(Float,       nullable=False)

    # No duplicate candles for the same symbol+timeframe+timestamp
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_candle"),
    )

    def __repr__(self):
        return f"<Candle {self.symbol} [{self.timeframe}] {self.timestamp} C={self.close}>"


class FetchLog(Base):
    """Tracks the last successful fetch for each symbol+timeframe."""
    __tablename__ = "fetch_log"

    id          = Column(Integer,  primary_key=True, autoincrement=True)
    symbol      = Column(String(20), nullable=False)
    timeframe   = Column(String(10), nullable=False)
    last_fetched= Column(DateTime,   nullable=False)
    candle_count= Column(Integer,    nullable=False, default=0)
    status      = Column(String(20), nullable=False, default="ok")  # ok | error
    notes       = Column(Text,       nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", name="uq_fetch_log"),
    )


# ── Engine & Session factory ──────────────────────────────────────

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # needed for SQLite
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialised ✅")


def get_session() -> Session:
    """Get a DB session. Always use as a context manager."""
    return SessionLocal()
