#!/usr/bin/env python3
"""
Local editor for property JSON files. No extra packages.

  python3 edit_server.py

Open http://127.0.0.1:8766/ — only listens on localhost.

Live preview: iframe shows HTML from disk (GET) or from the current form (POST
/api/preview-html, debounced) for WYSIWYG while editing. Save as ZIP posts edited
HTML and bundles local static/ assets.
"""

from __future__ import annotations

import base64
import io
import json
import mimetypes
import re
import sys
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from build import create_jinja_env, load_site, render_property_html

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ADMIN = ROOT / "admin"
STATIC = ROOT / "static"
ASSETS_PHOTOS = ROOT / "assets" / "photos"
ASSETS_BROKERS = ROOT / "assets" / "brokers"
BROKER_PRESETS_PATH = DATA / "broker_presets.json"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAX_BODY_JSON = 2_000_000
MAX_BODY_PREVIEW = 3_000_000
MAX_BODY_ZIP_EXPORT = 12_000_000
MAX_BODY_UPLOAD = 18 * 1024 * 1024
MAX_IMAGE_BYTES = 12 * 1024 * 1024
_UPLOAD_EXT = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})

# Full URL prefix the browser puts in src/href for preview assets
_DEV_ASSET_URL_PREFIX = re.compile(r"https?://127\.0\.0\.1:\d+/dev-asset/")
_ATTR_STATIC = re.compile(
    r'(?:src|href)\s*=\s*([\'"])(static/[^\'"]+)\1',
    re.IGNORECASE,
)

_jinja_env = None


def get_jinja_env():
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = create_jinja_env()
    return _jinja_env


def rewrite_preview_asset_urls(html: str) -> str:
    """Turn ../static/… into /dev-asset/static/… for same-origin iframe loading."""
    return (
        html.replace('src="../static/', 'src="/dev-asset/static/')
        .replace("src='../static/", "src='/dev-asset/static/")
        .replace('href="../static/', 'href="/dev-asset/static/')
        .replace("href='../static/", "href='/dev-asset/static/")
    )


def strip_editor_markup(html: str) -> str:
    html = re.sub(r"\s+contenteditable\s*=\s*\"[^\"]*\"", "", html, flags=re.I)
    html = re.sub(r"\s+contenteditable\s*=\s*'[^']*'", "", html, flags=re.I)
    html = re.sub(r"\s+spellcheck\s*=\s*\"[^\"]*\"", "", html, flags=re.I)
    html = re.sub(r"\s+spellcheck\s*=\s*'[^']*'", "", html, flags=re.I)
    return html


def normalize_html_for_zip(html: str) -> str:
    html = _DEV_ASSET_URL_PREFIX.sub("", html)
    html = html.replace('="/dev-asset/static/', '="static/')
    html = html.replace("='/dev-asset/static/", "='static/")
    html = html.replace('href="../static/', 'href="static/')
    html = html.replace("href='../static/", "href='static/")
    html = html.replace('src="../static/', 'src="static/')
    html = html.replace("src='../static/", "src='static/")
    return html


def collect_static_paths_from_html(html: str) -> set[str]:
    found: set[str] = set()
    for m in _ATTR_STATIC.finditer(html):
        path = m.group(2)
        if ".." in path or path.startswith("//"):
            continue
        found.add(path)
    return found


def resolve_local_static(relpath: str) -> Path | None:
    """Map static/css/… static/photos/… etc. to a file under the repo."""
    parts = tuple(Path(relpath).parts)
    if ".." in parts or not parts or parts[0] != "static":
        return None
    if len(parts) < 3:
        return None
    branch = parts[1]
    rest = Path(*parts[2:]) if len(parts) > 2 else Path()
    static_root = ROOT / "static"

    if branch == "css":
        p = static_root / "css" / rest
        return p if p.is_file() else None
    if branch == "photos":
        for base in (ROOT / "assets" / "photos", static_root / "photos"):
            p = base / rest
            if p.is_file():
                return p
        return None
    if branch == "brokers":
        for base in (ROOT / "assets" / "brokers", static_root / "brokers"):
            p = base / rest
            if p.is_file():
                return p
        return None
    if branch == "qr":
        p = ROOT / "dist" / "static" / "qr" / rest
        return p if p.is_file() else None

    p = static_root / Path(*parts[1:])
    return p if p.is_file() else None


def build_listing_zip_bytes(html: str) -> tuple[bytes, list[str]]:
    """
    Return (zip_bytes, missing_static_paths) — missing paths are logged by caller.
    """
    html = normalize_html_for_zip(html)
    html = strip_editor_markup(html)
    if "<html" not in html.lower():
        raise ValueError("HTML must include an <html> element")

    paths = collect_static_paths_from_html(html)
    paths.add("static/css/property.css")

    missing: list[str] = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", html)
        for rel in sorted(paths):
            fs_path = resolve_local_static(rel)
            if fs_path is None:
                missing.append(rel)
                continue
            zf.write(fs_path, rel)

    return buf.getvalue(), missing


def prepare_property_for_preview(raw: dict) -> dict:
    """Clone and fill defaults so Jinja can render incomplete draft JSON."""
    prop = json.loads(json.dumps(raw)) if isinstance(raw, dict) else {}
    if not prop.get("slug"):
        prop["slug"] = "preview"
    if not isinstance(prop.get("hero_image"), dict):
        prop["hero_image"] = {"src": "", "alt": ""}
    hi = prop["hero_image"]
    hi.setdefault("src", "")
    hi.setdefault("alt", "")
    if not isinstance(prop.get("intro_paragraphs"), list):
        prop["intro_paragraphs"] = []
    if not isinstance(prop.get("facts"), list):
        prop["facts"] = []
    return prop


def render_preview_document(prop: dict) -> str:
    site = load_site()
    env = get_jinja_env()
    p = prepare_property_for_preview(prop)
    html = render_property_html(
        env,
        site,
        p,
        "/dev-asset/static/css/property.css",
    )
    return rewrite_preview_asset_urls(html)


def sanitize_upload_basename(name: str) -> str | None:
    base = Path(name).name
    if not base or len(base) > 140 or ".." in base:
        return None
    suf = Path(base).suffix.lower()
    if suf not in _UPLOAD_EXT:
        return None
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(base).stem).strip("-")
    if not stem:
        stem = "photo"
    return (stem[:72] + suf).lower() if stem[:72] else None


def unique_dest_path(dest_dir: Path, basename: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    p = dest_dir / basename
    if not p.exists():
        return p
    stem, suf = Path(basename).stem, Path(basename).suffix
    for i in range(2, 10000):
        cand = dest_dir / f"{stem}-{i}{suf}"
        if not cand.exists():
            return cand
    msg = "could not allocate unique filename"
    raise OSError(msg)


def safe_zip_filename_slug(slug: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", (slug or "listing").strip()).strip("-")
    return (s[:80] if s else "listing")


class Handler(BaseHTTPRequestHandler):
    server_version = "PropertyEditor/1.1"

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

    def _serve_dev_asset(self, subpath: str) -> None:
        rel = subpath.lstrip("/")
        if not rel or ".." in rel:
            self.send_error(400)
            return
        fs = resolve_local_static(rel)
        if fs is None or not fs.is_file():
            self.send_error(404)
            return
        ctype, _ = mimetypes.guess_type(str(fs))
        self._send(200, fs.read_bytes(), ctype or "application/octet-stream")

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

        if path.startswith("/dev-asset/"):
            self._serve_dev_asset(path[len("/dev-asset/") :])
            return

        if path == "/live-preview":
            qs = urllib.parse.parse_qs(parsed.query)
            slug = (qs.get("slug") or [None])[0]
            if not slug or not SLUG_RE.match(slug):
                self.send_error(400, "bad slug")
                return
            prop_path = DATA / f"{slug}.json"
            if not prop_path.is_file():
                self.send_error(404)
                return
            try:
                prop = json.loads(prop_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.send_error(500)
                return
            html = render_preview_document(prop)
            raw = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
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

        if path == "/api/broker-presets":
            presets: list = []
            if BROKER_PRESETS_PATH.is_file():
                try:
                    obj = json.loads(BROKER_PRESETS_PATH.read_text(encoding="utf-8"))
                    raw = obj.get("presets", [])
                    presets = raw if isinstance(raw, list) else []
                except (json.JSONDecodeError, OSError):
                    presets = []
            self._json({"presets": presets})
            return

        if path == "/api/list-photos":
            files: list[str] = []
            if ASSETS_PHOTOS.is_dir():
                for f in sorted(ASSETS_PHOTOS.rglob("*")):
                    if not f.is_file():
                        continue
                    if any(
                        p.startswith(".")
                        for p in f.relative_to(ASSETS_PHOTOS).parts
                    ):
                        continue
                    if f.suffix.lower() not in _UPLOAD_EXT:
                        continue
                    files.append(f.relative_to(ASSETS_PHOTOS).as_posix())
            self._json({"files": files})
            return

        if path == "/api/list":
            items: list[dict] = []
            if DATA.is_dir():
                for f in sorted(DATA.glob("*.json")):
                    if f.name in ("site.json", "property.schema.json", "broker_presets.json"):
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
                self._json(
                    {
                        "brand": "Meadows-Hale",
                        "home_url": "https://www.meadows-hale.com",
                        "footer_label": "www.meadows-hale.com",
                        "properties_index_url": "../index.html",
                    }
                )
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

        if parsed.path == "/api/upload-photo":
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY_UPLOAD:
                self._json({"error": "payload too large"}, 413)
                return
            try:
                raw = self.rfile.read(length).decode("utf-8")
                data = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json({"error": "invalid JSON"}, 400)
                return
            filename = data.get("filename")
            b64 = data.get("data_base64")
            kind = data.get("kind", "gallery")
            if kind not in ("gallery", "broker"):
                kind = "gallery"
            if not isinstance(filename, str) or not isinstance(b64, str):
                self._json({"error": "filename and data_base64 required"}, 400)
                return
            safe_name = sanitize_upload_basename(filename)
            if not safe_name:
                self._json(
                    {"error": "invalid filename (use .jpg .png .webp .gif only)"},
                    400,
                )
                return
            try:
                raw_bytes = base64.b64decode(b64, validate=True)
            except (ValueError, TypeError):
                self._json({"error": "invalid base64"}, 400)
                return
            if len(raw_bytes) > MAX_IMAGE_BYTES:
                self._json({"error": "image too large (max 12 MB)"}, 413)
                return
            dest_root = ASSETS_PHOTOS if kind == "gallery" else ASSETS_BROKERS
            try:
                out_path = unique_dest_path(dest_root, safe_name)
                out_path.write_bytes(raw_bytes)
            except OSError as e:
                self._json({"error": str(e)}, 500)
                return
            sub = "photos" if kind == "gallery" else "brokers"
            src_json = f"../static/{sub}/{out_path.name}"
            self._json({"ok": True, "src": src_json, "filename": out_path.name})
            return

        if parsed.path == "/api/export-zip":
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY_ZIP_EXPORT:
                self._json({"error": "payload too large"}, 413)
                return
            try:
                raw = self.rfile.read(length).decode("utf-8")
                data = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json({"error": "invalid JSON"}, 400)
                return
            html = data.get("html")
            if not isinstance(html, str) or not html.strip():
                self._json({"error": "html required"}, 400)
                return
            slug = data.get("slug")
            if slug is not None and not isinstance(slug, str):
                self._json({"error": "bad slug"}, 400)
                return
            try:
                zbytes, missing = build_listing_zip_bytes(html)
            except ValueError as e:
                self._json({"error": str(e)}, 400)
                return
            if missing:
                sys.stderr.write(
                    "[export-zip] missing files (omitted from zip): %s\n" % ", ".join(missing[:20])
                )
                if len(missing) > 20:
                    sys.stderr.write("[export-zip] … and %s more\n" % (len(missing) - 20))

            name = safe_zip_filename_slug((slug or "listing").strip()) + "-listing.zip"
            cd = 'attachment; filename="%s"' % name.replace('"', "")
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(zbytes)))
            self.send_header("Content-Disposition", cd)
            self.end_headers()
            self.wfile.write(zbytes)
            return

        if parsed.path == "/api/preview-html":
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY_PREVIEW:
                self._json({"error": "payload too large"}, 413)
                return
            try:
                raw = self.rfile.read(length).decode("utf-8")
                prop = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json({"error": "invalid JSON"}, 400)
                return
            if not isinstance(prop, dict):
                self._json({"error": "body must be a JSON object"}, 400)
                return
            try:
                html = render_preview_document(prop)
            except Exception as e:  # noqa: BLE001 — local dev tool
                self._json({"error": str(e)}, 500)
                return
            raw = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return

        if parsed.path != "/api/property":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_JSON:
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
