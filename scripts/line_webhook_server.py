"""Local LINE webhook server to capture team member user IDs.

Usage:
  1. Add LINE_CHANNEL_SECRET to .env (LINE Developers > Basic settings)
  2. Start this server: python scripts/line_webhook_server.py
  3. Expose with ngrok: ngrok http 8080
  4. LINE Developers > Messaging API > Webhook URL:
       https://<ngrok-host>/callback
     Enable "Use webhook"
  5. Ask member to send any message to the official account
  6. Export IDs: python scripts/line_export_team_ids.py
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.line_team_registry import (  # noqa: E402
    REGISTRY_PATH,
    process_webhook_payload,
    verify_line_signature,
)

DEFAULT_PORT = 8080


class LineWebhookHandler(BaseHTTPRequestHandler):
    server_version = "LineWebhook/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[webhook] {self.address_string()} - {fmt % args}", flush=True)

    def _send(self, code: int, body: str = "", content_type: str = "text/plain") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            lines = [
                "LINE webhook server is running.",
                "POST /callback with LINE webhook events.",
                f"Registry: {REGISTRY_PATH}",
                "",
                "ngrok example: ngrok http %s" % os.getenv("LINE_WEBHOOK_PORT", DEFAULT_PORT),
            ]
            self._send(200, "\n".join(lines))
            return
        self._send(404, "not found")

    def do_POST(self) -> None:
        if self.path not in ("/callback", "/webhook"):
            self._send(404, "not found")
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else b""
        signature = self.headers.get("X-Line-Signature", "")
        secret = os.getenv("LINE_CHANNEL_SECRET", "").strip()

        if not secret:
            print("[webhook] ERROR: LINE_CHANNEL_SECRET missing in .env", flush=True)
            self._send(500, "channel secret not configured")
            return

        if not verify_line_signature(body, signature, secret):
            print("[webhook] ERROR: invalid signature", flush=True)
            self._send(403, "invalid signature")
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send(400, "invalid json")
            return

        user_ids = process_webhook_payload(payload)
        for uid in user_ids:
            print(f"[webhook] recorded user_id={uid}", flush=True)

        self._send(200, "ok")


def main() -> None:
    port = int(os.getenv("LINE_WEBHOOK_PORT", str(DEFAULT_PORT)))
    server = HTTPServer(("0.0.0.0", port), LineWebhookHandler)
    print("=== LINE webhook server ===", flush=True)
    print(f"Listening on http://127.0.0.1:{port}/callback", flush=True)
    print("Set LINE Developers webhook URL to https://<public-host>/callback", flush=True)
    print(f"Registry file: {REGISTRY_PATH}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)


if __name__ == "__main__":
    main()
