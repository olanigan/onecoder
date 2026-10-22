"""Read-only HTTP server for the work graph. Stdlib only. Binds loopback by default."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .snapshot import snapshot

PAGE = Path(__file__).with_name("page.html")
CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"


class _Handler(BaseHTTPRequestHandler):
    root: Path = Path(".")

    def do_GET(self):  # noqa: N802 (stdlib naming)
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE.read_bytes())
        elif path == "/api/graph":
            body = json.dumps(snapshot(self.root), indent=2).encode()
            self._send(200, "application/json", body, cache="no-store")
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def _send(self, status, ctype, body, cache="no-cache"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # keep the terminal quiet
        return


def make_server(root: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = type("VizHandler", (_Handler,), {"root": root})
    return ThreadingHTTPServer((host, port), handler)
