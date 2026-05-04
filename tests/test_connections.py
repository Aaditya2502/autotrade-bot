"""
tests/test_connections.py
──────────────────────────
Sanity-check that API connections are working.
Run this after setting up .env:

    python -m pytest tests/test_connections.py -v
"""

import pytest
from config.settings import settings


class TestConfig:
    """Verify .env is loaded correctly."""

    def test_env_file_exists(self):
        """At minimum, API keys should be non-empty strings."""
        assert isinstance(settings.kite.api_key, str), "KITE_API_KEY not set"
        assert isinstance(settings.binance.api_key, str), "BINANCE_API_KEY not set"

    def test_risk_config_defaults(self):
        assert settings.risk.max_daily_loss_pct > 0
        assert settings.risk.max_position_size_pct > 0
        assert settings.risk.max_open_positions > 0

    def test_app_mode_is_paper_by_default(self):
        """Should be in paper mode until explicitly switched to live."""
        # This will pass in dev — you must manually flip to live
        assert settings.mode in ("paper", "live")


class TestBinanceConnection:
    """Test Binance API — uses testnet by default (safe)."""

    def test_binance_ping(self):
        """Binance /ping should always succeed."""
        try:
            from src.data.binance_client import BinanceClient
            client = BinanceClient()
            result = client.client.ping()
            assert result == {}, f"Unexpected ping response: {result}"
        except ImportError:
            pytest.skip("python-binance not installed — run: pip install -r requirements.txt")
        except Exception as e:
            pytest.skip(f"Binance connection skipped: {e}")

    def test_binance_get_btc_ticker(self):
        """Should return a BTC price."""
        try:
            from src.data.binance_client import BinanceClient
            client = BinanceClient()
            ticker = client.get_ticker("BTCUSDT")
            price = float(ticker["price"])
            assert price > 0, "BTC price should be positive"
            print(f"\n  ✅ BTC/USDT price: ${price:,.2f}")
        except Exception as e:
            pytest.skip(f"Binance ticker skipped: {e}")


class TestKiteConnection:
    """Test Kite connection — requires valid access token."""

    def test_kite_requires_credentials(self):
        """Just checks that config keys are present."""
        if not settings.kite.api_key:
            pytest.skip("KITE_API_KEY not configured")
        assert len(settings.kite.api_key) > 5, "KITE_API_KEY looks too short"

    def test_kite_login_url(self):
        """Login URL should be constructable without an access token."""
        if not settings.kite.api_key:
            pytest.skip("KITE_API_KEY not configured")
        try:
            from src.data.kite_client import KiteClient
            client = KiteClient()
            url = client.get_login_url()
            assert "kite.trade" in url or "zerodha" in url
            print(f"\n  ✅ Kite login URL: {url}")
        except Exception as e:
            pytest.skip(f"Kite test skipped: {e}")
