"""Lightweight symmetric encryption for the credentials file.

Uses Fernet (AES-128-CBC + HMAC). The master key lives in the ENCRYPTION_KEY
env var; if it's missing, we generate and persist one on first run (dev only).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import PROJECT_ROOT
from .logger import get_logger

log = get_logger(__name__)

CRED_FILE = PROJECT_ROOT / "credentials.enc"
ENV_KEY = "ENCRYPTION_KEY"


def _load_key() -> bytes:
    key = os.getenv(ENV_KEY)
    if key:
        return key.encode()
    # Dev fallback — auto-generate and persist to .env so subsequent runs work
    new_key = Fernet.generate_key()
    env_path = PROJECT_ROOT / ".env"
    line = f"{ENV_KEY}={new_key.decode()}\n"
    if env_path.exists():
        with env_path.open("a", encoding="utf-8") as f:
            f.write("\n# auto-generated\n" + line)
    else:
        with env_path.open("w", encoding="utf-8") as f:
            f.write(line)
    os.environ[ENV_KEY] = new_key.decode()
    log.warning("ENCRYPTION_KEY missing — generated a new one and appended to .env")
    return new_key


def _fernet() -> Fernet:
    return Fernet(_load_key())


def save_credentials(data: dict[str, Any]) -> None:
    payload = json.dumps(data, indent=2).encode()
    token = _fernet().encrypt(payload)
    CRED_FILE.write_bytes(token)
    log.info("Credentials saved (encrypted) to %s", CRED_FILE)


def load_credentials() -> dict[str, Any]:
    if not CRED_FILE.exists():
        return {}
    try:
        raw = CRED_FILE.read_bytes()
        return json.loads(_fernet().decrypt(raw).decode())
    except (InvalidToken, ValueError) as e:
        log.error("Failed to decrypt credentials: %s", e)
        return {}


def mask(value: str, keep: int = 2) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep * 2)}{value[-keep:]}"
