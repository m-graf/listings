# property-coper-web

Templatized **land / property listing** pages. One JSON file per property → static HTML.

The **blueprint** matches the section structure of [The Wings Group](https://www.wingsgroupllc.com) style listings (hero, meta, sticky nav, intro + broker, gallery, facts, map, downloads, detail tabs). This project does **not** bundle their CSS/JS or WordPress markup—only a parallel layout and class naming for familiarity.

## Quick start

```bash
cd ~/Personal/property-coper-web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python build.py
open dist/index.html
# or: python3 -m http.server 8765 -d dist
```

## Simple editor (no frameworks)

1. Start the local server (stdlib only, **localhost only**):

   ```bash
   python3 edit_server.py
   ```

2. Open **http://127.0.0.1:8766/** in your browser.

3. Choose a listing from the dropdown, edit fields, click **Save** (writes `data/<slug>.json`).

4. Run **`python build.py`** to refresh `dist/`.

New listing: leave dropdown on “New”, enter a **slug**, fill the form, **Save**.

## Add a property

1. Copy `data/southern-farmhouse-revival.json` to `data/your-slug.json` (or start from **New** in the editor).
2. Set `"slug"` (used for URL path) and fill fields. Omit or null `map_embed_url`, `downloads`, `brokers_comment`, etc. to hide sections.
3. Run `python build.py` → `dist/<slug>/index.html`.

See **`docs/BLUEPRINT.md`** for the field → section map.

## Inspect the original webarchive

```bash
python3 scripts/inspect_webarchive.py ~/Downloads/the-wings-group.webarchive -o reference/main.html
```

## Layout files

| Path | Role |
|------|------|
| `data/site.json` | Brand name + footer links |
| `data/*.json` | Property payloads (exclude `site.json` from slug list) |
| `templates/property.html.j2` | Listing page |
| `templates/index.html.j2` | Listing of all properties |
| `static/css/property.css` | Theme (replace to match your brand) |

## Publish with GitHub Pages

`dist/` is gitignored; the site is built in CI and deployed from the **`dist/`** output.

1. Push this repo to GitHub (e.g. `your-name/property-coper-web`).
2. **Settings → Pages → Build and deployment:** set **Source** to **GitHub Actions** (not “Deploy from a branch”).
3. Push to **`main`** (or merge a PR). The workflow **Deploy Pages** runs `python build.py` and publishes `dist/`.
4. After the workflow succeeds, open the site URL shown under **Settings → Pages**.

Listing index: `https://<user>.github.io/<repo>/`  
Southern Farmhouse example: `https://<user>.github.io/<repo>/southern-farmhouse-revival/` (paths match `dist/`).

## Notes

- Remote images in sample JSON point at Wings / Unsplash URLs for demo only; host assets yourself for production.
- **Google Drive:** Set `gallery_drive_url` to a shared folder (or gallery) link to show an “Open gallery on Google Drive” button. You can still list `gallery_images` with **file** share URLs (`drive.google.com/file/d/…`); the build uses Google’s thumbnail endpoint for `<img>`. Files must be shared **Anyone with the link** or thumbnails may not load.
- Swiper/Fancybox from the original site are not included; the gallery is a responsive CSS grid with links to full images. You can add a lightbox library later.
