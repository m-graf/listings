#!/usr/bin/env python3
"""Render JSON property data into static HTML under dist/."""

from __future__ import annotations

import copy
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent

# Google Drive file share URLs → thumbnail for <img>; link href uses /file/d/ID/view
_DRIVE_FILE_PATH = re.compile(
    r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
_DRIVE_OPEN_ID = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)", re.IGNORECASE)
_HERO_STATIC_PHOTO = re.compile(r"^\.\./static/photos/([^/?#]+)$")
HERO_MAX_DIMENSION = 1920
HERO_JPEG_QUALITY = 86
# Skip re-encoding heroes already this small (bytes), unless dimensions exceed max
HERO_SKIP_JPEG_UNDER_BYTES = 650_000


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


def listing_inquiry_mailto_filter(email: str, listing: dict) -> str:
    """mailto: with subject (location) and body prefilled from listing JSON."""
    if not email or not isinstance(listing, dict):
        return "#"
    addr = str(email).strip()
    if not addr:
        return "#"

    title = (listing.get("title") or "").strip()
    loc = (listing.get("location") or "").strip()
    acres = (listing.get("acres_label") or "").strip()
    price = (listing.get("price_label") or "").strip()
    status = (listing.get("status") or "").strip()

    if loc:
        subject = f"Inquiry: {loc}"
    elif title:
        subject = f"Inquiry: {title}"
    else:
        subject = "Property inquiry"

    lines = [
        "I am writing about the following listing:",
        "",
        f"Property: {title or '—'}",
        f"Location: {loc or '—'}",
    ]
    if acres:
        lines.append(f"Size: {acres}")
    if price:
        lines.append(f"Price: {price}")
    if status:
        lines.append(f"Status: {status}")
    lines.extend(
        [
            "",
            "Hello,",
            "",
            "I would like more information about this property.",
            "",
            "",
        ]
    )
    body = "\n".join(lines)

    q = f"subject={quote(subject, safe='')}&body={quote(body, safe='')}"
    return f"mailto:{addr}?{q}"


TEMPLATES = ROOT / "templates"
DATA = ROOT / "data"
DIST = ROOT / "dist"
STATIC = ROOT / "static"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_site() -> dict:
    site_path = DATA / "site.json"
    return load_json(site_path) if site_path.is_file() else {"brand": "Properties"}


def create_jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml", "j2"]),
    )
    env.filters["gallery_img_src"] = gallery_img_src
    env.filters["gallery_link_href"] = gallery_link_href
    env.filters["listing_inquiry_mailto"] = listing_inquiry_mailto_filter
    env.filters["tojson"] = _tojson_filter
    return env


def render_property_html(
    env: Environment,
    site: dict,
    prop: dict,
    css_href: str,
    *,
    deep_copy: bool = True,
) -> str:
    """Render listing HTML. Use deep_copy=True for preview (avoids mutating JSON-backed dict)."""
    if deep_copy:
        prop = copy.deepcopy(prop)
    images = prop.get("gallery_images")
    if isinstance(images, list):
        prop["gallery_images"] = [
            x
            for x in images
            if isinstance(x, dict) and str((x.get("src") or "")).strip()
        ]
    tpl = env.get_template("property.html.j2")
    return tpl.render(site=site, property=prop, css_href=css_href)


def _tojson_filter(value) -> Markup:
    """Safe JSON for embedding in <script> (Jinja has no built-in tojson)."""
    out = json.dumps(value, ensure_ascii=False)
    out = out.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup(out)


def optimize_hero_in_dist(prop: dict, dest_photos: Path) -> None:
    """Resize and JPEG-encode large local hero images under static/photos (updates prop in memory)."""
    try:
        from PIL import Image
    except ImportError:
        return
    hi = prop.get("hero_image")
    if not isinstance(hi, dict):
        return
    src = (hi.get("src") or "").strip()
    m = _HERO_STATIC_PHOTO.match(src)
    if not m:
        return
    in_path = dest_photos / m.group(1)
    if not in_path.is_file():
        return
    try:
        im = Image.open(in_path)
    except OSError:
        return

    w, h = im.size
    max_side = max(w, h)
    needs_resize = max_side > HERO_MAX_DIMENSION
    size_b = in_path.stat().st_size

    if im.mode == "P":
        im = im.convert("RGBA")
        w, h = im.size
        max_side = max(w, h)
        needs_resize = max_side > HERO_MAX_DIMENSION

    rgb = None
    if im.mode == "RGB":
        rgb = im
    elif im.mode == "RGBA":
        if im.getchannel("A").getextrema() == (255, 255):
            rgb = im.convert("RGB")
    elif im.mode == "L":
        rgb = im.convert("RGB")

    if rgb is not None:
        if needs_resize:
            scale = HERO_MAX_DIMENSION / float(max(rgb.size))
            rgb = rgb.resize(
                (max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale))),
                Image.Resampling.LANCZOS,
            )
        if (
            in_path.suffix.lower() in {".jpg", ".jpeg"}
            and not needs_resize
            and size_b < HERO_SKIP_JPEG_UNDER_BYTES
        ):
            return
        out_path = dest_photos / f"{in_path.stem}.jpg"
        rgb.save(
            out_path,
            "JPEG",
            quality=HERO_JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )
        if in_path.resolve() != out_path.resolve():
            in_path.unlink(missing_ok=True)
        hi["src"] = f"../static/photos/{out_path.name}"
        return

    if needs_resize:
        scale = HERO_MAX_DIMENSION / float(max_side)
        im = im.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )
        im.save(in_path, optimize=True)


_SLUG_FILE_SAFE = re.compile(r"[^a-z0-9-]+")


def attach_helpful_link_qr_svgs(prop: dict, slug: str, qr_dir: Path) -> None:
    """Write QR code SVGs for helpful_links hrefs; set link['qr_src'] for the template."""
    links = prop.get("helpful_links")
    if not isinstance(links, list):
        return
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
        from qrcode.image.svg import SvgPathImage
    except ImportError:
        for link in links:
            if isinstance(link, dict):
                link["qr_src"] = None
        return

    safe = _SLUG_FILE_SAFE.sub("-", (slug or "listing").lower()).strip("-") or "listing"
    qr_dir.mkdir(parents=True, exist_ok=True)

    for i, link in enumerate(links):
        if not isinstance(link, dict):
            continue
        href = (link.get("href") or "").strip()
        if not href:
            link["qr_src"] = None
            continue
        out_path = qr_dir / f"{safe}-{i}.svg"
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_M,
            box_size=4,
            border=2,
        )
        qr.add_data(href)
        qr.make(fit=True)
        img = qr.make_image(image_factory=SvgPathImage)
        with out_path.open("wb") as f:
            img.save(f)
        link["qr_src"] = f"../static/qr/{out_path.name}"


def resize_broker_images(dest: Path, max_dim: int = 800) -> None:
    """Shrink large broker headshots in dist (macOS sips). Skips non-macOS or failure."""
    if platform.system() != "Darwin":
        return
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    for f in dest.iterdir():
        if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in exts:
            continue
        try:
            subprocess.run(
                ["sips", "-Z", str(max_dim), str(f)],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            pass


def main() -> int:
    if not DATA.is_dir():
        print("Missing data/ directory", file=sys.stderr)
        return 1

    env = create_jinja_env()
    site = load_site()

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    (DIST / ".nojekyll").touch()  # GitHub Pages: serve static files as-is
    if STATIC.is_dir():
        shutil.copytree(STATIC, DIST / "static")

    assets_photos = ROOT / "assets" / "photos"
    if assets_photos.is_dir():
        dest_photos = DIST / "static" / "photos"
        dest_photos.mkdir(parents=True, exist_ok=True)
        for f in assets_photos.iterdir():
            if f.is_file() and not f.name.startswith("."):
                shutil.copy2(f, dest_photos / f.name)

    assets_brokers = ROOT / "assets" / "brokers"
    if assets_brokers.is_dir():
        dest_brokers = DIST / "static" / "brokers"
        dest_brokers.mkdir(parents=True, exist_ok=True)
        for f in assets_brokers.iterdir():
            if f.is_file() and not f.name.startswith("."):
                shutil.copy2(f, dest_brokers / f.name)
        resize_broker_images(dest_brokers)

    listings: list[dict] = []
    dest_photos = DIST / "static" / "photos"

    for path in sorted(DATA.glob("*.json")):
        if path.name in ("site.json", "property.schema.json", "broker_presets.json"):
            continue
        prop = load_json(path)
        slug = prop.get("slug") or path.stem
        prop.setdefault("slug", slug)
        images = prop.get("gallery_images")
        if isinstance(images, list):
            # Preserve JSON order from the editor (manual ordering). Drop empty entries.
            prop["gallery_images"] = [
                x
                for x in images
                if isinstance(x, dict) and str((x.get("src") or "")).strip()
            ]
        if dest_photos.is_dir():
            optimize_hero_in_dist(prop, dest_photos)
        attach_helpful_link_qr_svgs(prop, slug, DIST / "static" / "qr")
        listings.append(
            {
                "slug": slug,
                "title": prop.get("title", slug),
                "location": prop.get("location", ""),
            }
        )

        html = render_property_html(
            env,
            site,
            prop,
            "../static/css/property.css",
            deep_copy=False,
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
