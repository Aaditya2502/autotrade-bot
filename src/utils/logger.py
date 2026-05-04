"""
src/utils/logger.py
───────────────────
Centralised logger using loguru.
Import `logger` anywhere in the project.
"""

import sys
from pathlib import Path
from loguru import logger
from config.settings import settings

# Remove default handler
logger.remove()

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Console output — coloured, human-readable
logger.add(
    sys.stdout,
    level=settings.log_level,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> — <level>{message}</level>",
    colorize=True,
)

# File output — full detail, rotated daily, kept 30 days
logger.add(
    LOG_DIR / "autotrade_{time:YYYY-MM-DD}.log",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} — {message}",
    rotation="00:00",
    retention="30 days",
    compression="zip",
)

# Separate error log for quick debugging
logger.add(
    LOG_DIR / "errors.log",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} — {message}",
    rotation="10 MB",
    retention="60 days",
)

__all__ = ["logger"]
