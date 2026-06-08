"""MT5 client interface (real + mock) and a factory that picks one.

The rest of the app always talks to ``MT5Client``. When ``MetaTrader5`` is
importable and a terminal is reachable, the real client is used; otherwise the
mock client provides a deterministic but realistic simulation.
"""
from .factory import MT5Client, build_client

__all__ = ["MT5Client", "build_client"]
