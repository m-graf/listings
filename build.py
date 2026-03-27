#!/usr/bin/env python3
"""Render JSON property data into static HTML under dist/."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent

# Google Drive file share URLs → thumbnail for <img>; link href uses /file/d/ID/view
_DRIVE_FILE_PATH = re.compile(
    r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
_DRIVE_OPEN_ID = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)", re.IGNORECASE)


def extract_drive_file_id(url: str) -> str | None:
    if not url or "drive.google.com" not in url.lower():
        return None
    m = _DRIVE_FILE_PATH.search(url)
    if m:
        return m.group(1)
    if "/file/d/" not in url.lower():
        m = _DRIVE_OPEN_ID.search(url)
        if m:
            return m.group(1)
    return None


def gallery_img_src(url: str) -> str:
    fid = extract_drive_file_id(url)
    if fid:
        return f"https://drive.google.com/thumbnail?id={fid}&sz=w2000"
    return url


def gallery_link_href(url: str) -> str:
    fid = extract_drive_file_id(url)
    if fid:
        return f"https://drive.google.com/file/d/{fid}/view"
    return url


TEMPLATES = ROOT / "templates"
DATA = ROOT / "data"
DIST = ROOT / "dist"
STATIC = ROOT / "static"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    if not DATA.is_dir():
        print("Missing data/ directory", file=sys.stderr)
        return 1

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml", "j2"]),
    )
    env.filters["gallery_img_src"] = gallery_img_src
    env.filters["gallery_link_href"] = gallery_link_href

    site_path = DATA / "site.json"
    site = load_json(site_path) if site_path.is_file() else {"brand": "Properties"}

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    if STATIC.is_dir():
        shutil.copytree(STATIC, DIST / "static")

    property_tpl = env.get_template("property.html.j2")
    listings: list[dict] = []

    for path in sorted(DATA.glob("*.json")):
        if path.name in ("site.json", "property.schema.json"):
            continue
        prop = load_json(path)
        slug = prop.get("slug") or path.stem
        prop.setdefault("slug", slug)
        listings.append(
            {
                "slug": slug,
                "title": prop.get("title", slug),
                "location": prop.get("location", ""),
            }
        )

        html = property_tpl.render(
            site=site,
            property=prop,
            css_href="../static/css/property.css",
        )
        out_dir = DIST / slug
        out_dir.mkdir(parents=True)
        (out_dir / "index.html").write_text(html, encoding="utf-8")
        print(f"Wrote {out_dir / 'index.html'}")

    listings.sort(key=lambda x: x["title"].lower())
    index_tpl = env.get_template("index.html.j2")
    index_html = index_tpl.render(
        site=site,
        listings=listings,
        css_href="static/css/property.css",
    )
    (DIST / "index.html").write_text(index_html, encoding="utf-8")
    print(f"Wrote {DIST / 'index.html'}")

    print("\nOpen dist/index.html in a browser, or: python3 -m http.server -d dist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
