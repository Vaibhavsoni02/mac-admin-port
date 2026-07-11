#!/usr/bin/env python3
"""
Local Mac agent — exposes machine scan as JSON for Streamlit Cloud (via tunnel).

  python3 agent.py
  # http://127.0.0.1:4041/api/snapshot
  # http://127.0.0.1:4041/api/network
  # http://127.0.0.1:4041/api/health
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from admin_core import collect_all, collect_network

HOST = os.environ.get("AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("AGENT_PORT", "4041"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[agent] {self.address_string()} {fmt % args}")

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self._send(200, {"ok": True, "role": "mac-admin-agent", "port": PORT})
                return
            if path == "/api/snapshot":
                self._send(200, collect_all())
                return
            if path == "/api/network":
                self._send(200, collect_network())
                return
            self._send(404, {"error": "not found", "paths": ["/api/health", "/api/snapshot", "/api/network"]})
        except Exception as e:
            self._send(500, {"error": str(e)})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Mac Admin Agent → http://{HOST}:{PORT}")
    print("Tunnel example: cloudflared tunnel --url http://127.0.0.1:4041")
    print("Then set Streamlit secret AGENT_URL to the https://….trycloudflare.com URL")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
