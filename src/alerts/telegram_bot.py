"""
src/alerts/telegram_bot.py
───────────────────────────
Telegram bot for trade alerts.
Sends notifications when:
  - A trade is opened
  - A trade closes (with P&L)
  - Stop loss or take profit hit
  - Circuit breaker trips
  - Daily summary

Setup:
  1. Message @BotFather on Telegram → /newbot
  2. Copy the token into .env as TELEGRAM_BOT_TOKEN
  3. Start a chat with your bot, then get your chat ID:
     https://api.telegram.org/bot<TOKEN>/getUpdates
  4. Copy the chat_id into .env as TELEGRAM_CHAT_ID
"""

import requests
from datetime import datetime
from src.utils.logger import logger
from config.settings import settings


class TelegramAlert:
    """Sends trade notifications via Telegram."""

    def __init__(self):
        self.token   = settings.telegram.bot_token
        self.chat_id = settings.telegram.chat_id
        self.enabled = bool(self.token and self.chat_id)

        if self.enabled:
            logger.info("Telegram alerts enabled ✅")
        else:
            logger.info("Telegram alerts disabled (no token/chat_id in .env)")

    def send(self, message: str) -> bool:
        """Send a message to Telegram. Returns True if successful."""
        if not self.enabled:
            logger.debug(f"[Telegram disabled] {message}")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id":    self.chat_id,
            "text":       message,
            "parse_mode": "HTML",
        }

        try:
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code == 200:
                logger.debug("Telegram alert sent ✅")
                return True
            else:
                logger.warning(f"Telegram failed: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.warning(f"Telegram error: {e}")
            return False

    # ── Pre-formatted alert messages ─────────────────────────────

    def trade_opened(self, symbol, side, qty, price, sl, tp, strategy):
        icon = "🟢" if side == "long" else "🔴"
        msg = (
            f"{icon} <b>TRADE OPENED</b>\n"
            f"Symbol:   {symbol}\n"
            f"Side:     {side.upper()}\n"
            f"Qty:      {qty}\n"
            f"Entry:    ₹{price:,.2f}\n"
            f"Stop:     ₹{sl:,.2f}\n"
            f"Target:   ₹{tp:,.2f}\n"
            f"Strategy: {strategy}\n"
            f"Time:     {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send(msg)

    def trade_closed(self, symbol, exit_price, pnl, pnl_pct, reason):
        icon = "✅" if pnl > 0 else "❌"
        msg = (
            f"{icon} <b>TRADE CLOSED</b>\n"
            f"Symbol:  {symbol}\n"
            f"Exit:    ₹{exit_price:,.2f}\n"
            f"P&L:     ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
            f"Reason:  {reason}\n"
            f"Time:    {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send(msg)

    def circuit_breaker_tripped(self, reason):
        msg = (
            f"🚨 <b>CIRCUIT BREAKER TRIPPED</b>\n"
            f"Reason: {reason}\n"
            f"All trading halted!\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send(msg)

    def daily_summary(self, portfolio_value, pnl, pnl_pct, trades, win_rate):
        icon = "📈" if pnl >= 0 else "📉"
        msg = (
            f"{icon} <b>DAILY SUMMARY</b>\n"
            f"Portfolio: ₹{portfolio_value:,.0f}\n"
            f"Day P&L:   ₹{pnl:+,.0f} ({pnl_pct:+.2f}%)\n"
            f"Trades:    {trades}\n"
            f"Win Rate:  {win_rate:.0f}%\n"
            f"Date:      {datetime.now().strftime('%d %b %Y')}"
        )
        return self.send(msg)

    def test_connection(self) -> bool:
        """Send a test message to verify the bot is working."""
        return self.send(
            "🤖 <b>AutoTrade Bot Connected!</b>\n"
            "Trade alerts are now active.\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
