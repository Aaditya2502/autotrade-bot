"""
config/settings.py
──────────────────
Central configuration loader.
Reads from .env and exposes typed settings across the app.
"""

import os
from dotenv import load_dotenv
from dataclasses import dataclass, field
from pathlib import Path

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")


@dataclass
class KiteConfig:
    api_key: str = field(default_factory=lambda: os.getenv("KITE_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("KITE_API_SECRET", ""))
    access_token: str = field(default_factory=lambda: os.getenv("KITE_ACCESS_TOKEN", ""))


@dataclass
class BinanceConfig:
    api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_API_SECRET", ""))
    testnet: bool = field(default_factory=lambda: os.getenv("BINANCE_TESTNET", "true").lower() == "true")


@dataclass
class TelegramConfig:
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))


@dataclass
class RiskConfig:
    max_daily_loss_pct: float = field(default_factory=lambda: float(os.getenv("MAX_DAILY_LOSS_PCT", "3.0")))
    max_position_size_pct: float = field(default_factory=lambda: float(os.getenv("MAX_POSITION_SIZE_PCT", "2.0")))
    max_open_positions: int = field(default_factory=lambda: int(os.getenv("MAX_OPEN_POSITIONS", "5")))


@dataclass
class AppConfig:
    mode: str = field(default_factory=lambda: os.getenv("APP_MODE", "paper"))          # paper | live
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///data/autotrade.db"))

    kite: KiteConfig = field(default_factory=KiteConfig)
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    def is_paper(self) -> bool:
        return self.mode == "paper"

    def is_live(self) -> bool:
        return self.mode == "live"

    def validate(self):
        """Raise early if critical keys are missing."""
        errors = []
        if not self.kite.api_key:
            errors.append("KITE_API_KEY is missing")
        if not self.binance.api_key:
            errors.append("BINANCE_API_KEY is missing")
        if self.is_live() and not self.kite.access_token:
            errors.append("KITE_ACCESS_TOKEN is required in live mode")
        if errors:
            raise EnvironmentError(f"Config errors:\n" + "\n".join(f"  - {e}" for e in errors))


# Singleton — import this everywhere
settings = AppConfig()
