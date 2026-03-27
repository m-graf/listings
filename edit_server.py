#!/usr/bin/env python3
"""
Local editor for property JSON files. No extra packages.

  python3 edit_server.py

Open http://127.0.0.1:8766/ — only listens on localhost.
"""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ADMIN = ROOT / "admin"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAX_BODY = 2_000_000


class Handler(BaseHTTPRequestHandler):
    server_version = "PropertyEditor/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: object, status: int = 200) -> None:
        raw = json.dumps(obj).encode("utf-8")
        self._send(status, raw, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            p = ADMIN / "index.html"
            if not p.is_file():
                self.send_error(500, "Missing admin/index.html")
                return
            b = p.read_bytes()
            self._send(200, b, "text/html; charset=utf-8")
            return

        if path.startswith("/admin/"):
            rel = path[7:].lstrip("/")
            if not rel or ".." in rel:
                self.send_error(400)
                return
            p = ADMIN / rel
            if not p.is_file():
                self.send_error(404)
                return
            ctype, _ = mimetypes.guess_type(str(p))
            self._send(200, p.read_bytes(), ctype or "application/octet-stream")
            return

        if path == "/api/list":
            items: list[dict] = []
            if DATA.is_dir():
                for f in sorted(DATA.glob("*.json")):
                    if f.name in ("site.json", "property.schema.json"):
                        continue
                    try:
                        d = json.loads(f.read_text(encoding="utf-8"))
                        items.append(
                            {
                                "slug": d.get("slug", f.stem),
                                "title": d.get("title", f.stem),
                            }
                        )
                    except (json.JSONDecodeError, OSError):
                        items.append({"slug": f.stem, "title": f.stem})
            self._json(items)
            return

        if path == "/api/site":
            p = DATA / "site.json"
            if p.is_file():
                self._json(json.loads(p.read_text(encoding="utf-8")))
            else:
                self._json({"brand": "Property Co", "home_url": "../index.html"})
            return

        if path.startswith("/api/property"):
            qs = urllib.parse.parse_qs(parsed.query)
            slug = (qs.get("slug") or [None])[0]
            if not slug or not SLUG_RE.match(slug):
                self._json({"error": "bad slug"}, 400)
                return
            p = DATA / f"{slug}.json"
            if not p.is_file():
                self._json({"error": "not found"}, 404)
                return
            self._json(json.loads(p.read_text(encoding="utf-8")))
            return

        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/property":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY:
            self._json({"error": "payload too large"}, 413)
            return

        try:
            raw = self.rfile.read(length).decode("utf-8")
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return

        slug = data.get("slug")
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            self._json({"error": "slug must be lowercase letters, numbers, hyphens"}, 400)
            return
        if slug == "site":
            self._json({"error": "reserved slug"}, 400)
            return

        DATA.mkdir(parents=True, exist_ok=True)
        out = DATA / f"{slug}.json"
        try:
            text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            out.write_text(text, encoding="utf-8")
        except OSError as e:
            self._json({"error": str(e)}, 500)
            return

        self._json({"ok": True, "slug": slug})


def main() -> None:
    host = "127.0.0.1"
    port = 8766
    if not ADMIN.joinpath("index.html").is_file():
        print("Missing admin/index.html", file=sys.stderr)
        sys.exit(1)
    httpd = HTTPServer((host, port), Handler)
    print(f"Property editor: http://{host}:{port}/")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
