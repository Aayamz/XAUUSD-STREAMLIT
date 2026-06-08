"""Factory: pick the right client based on env / availability."""
from __future__ import annotations

from typing import Any

from utils.config import get_trading_mode
from utils.encryption import load_credentials
from utils.logger import get_logger

log = get_logger(__name__)


# The interface both clients must implement. We don't use ABC to keep imports
# light; this is documentation.
MT5Client = Any  # duck-typed


def build_client() -> Any:
    """Return a connected MT5 client. Falls back to mock if anything fails."""
    mode = get_trading_mode()
    creds = load_credentials()

    if mode == "mock":
        log.info("TRADING_MODE=mock — using mock client")
        from .mock_client import MockMT5Client

        client = MockMT5Client()
        client.connect()
        return client

    # mode == "demo" — try real first
    try:
        from .real_client import RealMT5Client
    except Exception as e:  # noqa: BLE001
        log.warning("MetaTrader5 package not available: %s — falling back to mock", e)
        from .mock_client import MockMT5Client

        client = MockMT5Client()
        client.connect()
        return client

    login = creds.get("login") or 0
    password = creds.get("password", "")
    server = creds.get("server", "")
    path = creds.get("path", "")
    if not (login and password and server):
        log.warning("MT5 credentials incomplete — falling back to mock")
        from .mock_client import MockMT5Client

        client = MockMT5Client()
        client.connect()
        return client

    try:
        client = RealMT5Client(login=login, password=password, server=server, path=path)
        client.connect()
        return client
    except Exception as e:  # noqa: BLE001
        log.error("Failed to connect to real MT5: %s — falling back to mock", e)
        from .mock_client import MockMT5Client

        client = MockMT5Client()
        client.connect()
        return client
