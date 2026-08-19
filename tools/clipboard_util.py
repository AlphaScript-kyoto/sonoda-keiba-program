"""OS clipboard helper (Windows clip.exe)."""

from __future__ import annotations

import os
import subprocess
import sys

_T10_CLIPBOARD_OFF = frozenset({"0", "false", "no", "off"})


def t10_clipboard_enabled() -> bool:
    """Default on. Set T10_CLIPBOARD=0 to disable."""
    raw = os.getenv("T10_CLIPBOARD", "1").strip().lower()
    return raw not in _T10_CLIPBOARD_OFF


def copy_to_clipboard(text: str) -> bool:
    """Copy plain text to the system clipboard. Returns False if unsupported."""
    body = text.strip()
    if not body:
        return False
    if sys.platform == "win32":
        return _copy_windows(body)
    return False


def _copy_windows(text: str) -> bool:
    try:
        proc = subprocess.run(
            ["clip"],
            input=text.encode("utf-16le"),
            check=False,
            timeout=5,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False