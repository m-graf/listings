#!/usr/bin/env python3
"""Render JSON property data into static HTML under dist/."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
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
