#!/usr/bin/env python3
"""
Dump Safari .webarchive main HTML for inspection (e.g. to update docs/BLUEPRINT.md).

Usage:
  python3 scripts/inspect_webarchive.py ~/Downloads/page.webarchive
  python3 scripts/inspect_webarchive.py ~/Downloads/page.webarchive -o ./reference-main.html
"""

from __future__ import annotations

import argparse
import plistlib
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="Extract WebMainResource HTML from a .webarchive")
    p.add_argument("webarchive", type=Path)
    p.add_argument("-o", "--output", type=Path, default=Path("/tmp/webarchive-main.html"))
    args = p.parse_args()

    path = args.webarchive.expanduser().resolve()
    if not path.is_file():
        print(f"Not found: {path}", file=sys.stderr)
        return 1

    with path.open("rb") as f:
        pl = plistlib.load(f)

    mr = pl.get("WebMainResource") or pl.get("MainResource")
    if not mr:
        print("No WebMainResource in plist", file=sys.stderr)
        return 1

    subs = pl.get("WebSubresources") or []
    print("WebMainResource URL:", mr.get("WebResourceURL", "")[:120])
    print("MIME:", mr.get("WebResourceMIMEType"))
    print("Subresources:", len(subs))

    data = mr.get("WebResourceData")
    if not isinstance(data, (bytes, bytearray)):
        print("Main resource is not bytes", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"Wrote {args.output} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
