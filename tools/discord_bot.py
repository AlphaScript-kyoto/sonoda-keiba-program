"""Discord Webhook notifications (category-routed)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DISCORD_TEXT_LIMIT = 1900


@dataclass(frozen=True)
class DiscordSendResult:
    category: str
    status_code: int
    chunk: str


def _chunk_text(text: str, max_len: int = DISCORD_TEXT_LIMIT) -> list[str]:
    body = text.strip()
    if not body:
        return [""]
    if len(body) <= max_len:
        return [body]

    chunks: list[str] = []
    current = ""
    for line in body.splitlines():
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= max_len:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(line) > max_len:
            chunks.append(line[:max_len])
            line = line[max_len:]
        current = line
    if current:
        chunks.append(current)
    return chunks


def _env_key_for_category(category: str) -> str:
    normalized = "".join(
        ch if ("a" <= ch.lower() <= "z" or "0" <= ch <= "9") else "_"
        for ch in str(category or "").strip().lower()
    )
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    normalized = normalized.strip("_")
    return f"DISCORD_WEBHOOK_{normalized.upper()}"


def resolve_discord_webhook(category: str) -> str:
    """Resolve webhook by category, fallback to DISCORD_WEBHOOK_URL."""
    specific = os.getenv(_env_key_for_category(category), "").strip()
    if specific:
        return specific
    return os.getenv("DISCORD_WEBHOOK_URL", "").strip()


def send_discord_message(
    message: str,
    *,
    category: str,
    username: Optional[str] = None,
) -> list[DiscordSendResult]:
    """
    Send Discord webhook message for the given category.

    If no webhook is configured, returns an empty list.
    Raises RuntimeError on non-2xx.
    """
    webhook = resolve_discord_webhook(category)
    if not webhook:
        return []

    parts = [p for p in _chunk_text(message) if p]
    if not parts:
        parts = ["(empty)"]
    total = len(parts)
    name = username or os.getenv("DISCORD_BOT_NAME", "").strip() or "Sonoda Bot"

    results: list[DiscordSendResult] = []
    for idx, part in enumerate(parts):
        payload = {
            "username": name,
            "content": f"({idx + 1}/{total})\n{part}" if total > 1 else part,
        }
        resp = requests.post(webhook, json=payload, timeout=30)
        results.append(
            DiscordSendResult(
                category=category,
                status_code=resp.status_code,
                chunk=f"{idx + 1}/{total}",
            )
        )
        if resp.status_code < 200 or resp.status_code >= 300:
            raise RuntimeError(
                f"discord {category} failed: status={resp.status_code} body={resp.text}"
            )
    return results