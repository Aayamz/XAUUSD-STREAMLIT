"""Logs page — tail bot.log and trades.jsonl with download buttons."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from utils.config import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "logs"


def _tail(path: Path, n: int = 300) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 50_000))
            data = f.read().decode("utf-8", errors="ignore")
        return "\n".join(data.splitlines()[-n:])
    except Exception as e:  # noqa: BLE001
        return f"[error reading {path}: {e}]"


def render() -> None:
    from dashboard.styles import inject_global_styles
    inject_global_styles()

    st_autorefresh = st.toggle("Auto-refresh", value=True, key="logs_refresh")
    if st_autorefresh:
        from streamlit_autorefresh import st_autorefresh as _ar
        _ar(interval=5_000, key="logs_timer")

    st.subheader("bot.log")
    st.code(_tail(LOG_DIR / "bot.log", 500), language="log")
    if (LOG_DIR / "bot.log").exists():
        st.download_button(
            "Download bot.log",
            data=(LOG_DIR / "bot.log").read_bytes(),
            file_name="bot.log",
            mime="text/plain",
        )

    st.subheader("trades.jsonl")
    st.code(_tail(LOG_DIR / "trades.jsonl", 500), language="json")
    if (LOG_DIR / "trades.jsonl").exists():
        st.download_button(
            "Download trades.jsonl",
            data=(LOG_DIR / "trades.jsonl").read_bytes(),
            file_name="trades.jsonl",
            mime="application/x-ndjson",
        )
