# Meadows Hale Listings

Static **property listing** sites: one JSON file per listing → HTML in `dist/`. No app server required to serve the built pages.

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

## Add a listing

1. Copy `data/southern-farmhouse-revival.json` to `data/your-slug.json` (or start from **New** in the editor).
2. Set `"slug"` (used for the URL path) and fill fields. Omit or set `null` on `map_embed_url`, `downloads`, `brokers_comment`, etc. to hide sections.
3. Run `python build.py` → `dist/<slug>/index.html`.

See **`docs/BLUEPRINT.md`** for the field → section map.

## Layout files

| Path | Role |
|------|------|
| `data/site.json` | Brand, footer links, optional analytics |
| `data/*.json` | Listing payloads (`site.json` and `property.schema.json` are not listings) |
| `templates/property.html.j2` | Listing page |
| `templates/index.html.j2` | Index of all listings |
| `static/css/property.css` | Styles |
| `assets/photos/`, `assets/brokers/` | Optional local images copied into `dist/static/` at build time |

## Bootleg analytics (Google Forms)

Optional **privacy-light** page-load pings: a small script POSTs to a Google Form **`formResponse`** URL (no cookies, no third-party tracker). Applies to **every built page** (index + each listing) once configured in **`data/site.json`**.

1. Create a [Google Form](https://forms.google.com) with one or more questions (e.g. short answer **Slug**, paragraph **Log**, short answer **Title**).
2. **Response URL:** open the live form → **View page source** and find `form action=".../formResponse"`, e.g.  
   `https://docs.google.com/forms/d/e/1FAIpQLS…/formResponse`
3. **Entry IDs:** in the form editor, **⋮ → Get pre-filled link**, fill a field, submit; copy the URL query params. Each `entry.1234567890` maps to one field.
4. Add an **`analytics`** object to `site.json`:

```json
"analytics": {
  "form_action": "https://docs.google.com/forms/d/e/YOUR_FORM_KEY/formResponse",
  "fields": {
    "slug": "entry.1111111111",
    "title": "entry.2222222222",
    "log": "entry.3333333333"
  }
}
```

- **`log`** (or **`payload`**, **`detail`**, **`raw`**) → multi-line blob: time, slug, title, URL, referrer, viewport, screen, DPR, language, time zone, truncated User-Agent.
- **`slug`** / **`listing_slug`**, **`title`** / **`listing_title`**, **`page_url`** / **`url`**, **`referrer`** / **`ref`** → single values into separate columns.

Rebuild after editing `site.json`. Submissions are best-effort (`sendBeacon` / `fetch` + `no-cors`). Not a replacement for full analytics or consent flows.

## Publish with GitHub Pages

`dist/` is gitignored; CI builds and deploys **`dist/`**.

1. Push this repo to GitHub.
2. **Settings → Pages → Build and deployment:** set **Source** to **GitHub Actions**.
3. Push to **`main`**. The **Deploy Pages** workflow runs `python build.py` and publishes `dist/`.
4. Open the URL under **Settings → Pages** when the run succeeds.

Example URLs (replace user/repo):  
`https://<user>.github.io/<repo>/` (index) · `https://<user>.github.io/<repo>/southern-farmhouse-revival/` (a listing).

## Notes

- Prefer hosting images under `assets/` (or your own URLs) for production; remote URLs in JSON work if they stay reachable.
- **Google Drive:** `gallery_drive_url` can point at a shared folder for an “Open gallery” button. **`gallery_images`** can use **file** share links (`drive.google.com/file/d/…`); the build uses Google’s thumbnail URL for `<img>`. Files should be shared **Anyone with the link** or thumbnails may fail.
- Gallery is a responsive CSS grid with links to full images (no lightbox bundled).
