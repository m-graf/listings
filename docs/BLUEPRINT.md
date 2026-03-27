# Property listing page blueprint

Derived from structural analysis of **The Wings Group** property template  
(`the-wings-group.webarchive` → main URL: `…/properties/cloudland-pastures/`).

This repo is a **clean-room layout**: same information architecture and BEM-style class names for familiarity, **not** a pixel copy of their WordPress theme, fonts, or assets.

## Page regions (top → bottom)

| Order | Region | HTML hook (template) | Data source |
|------:|--------|----------------------|-------------|
| 1 | Full-bleed hero | `.hero`, `.hero__image`, `.page-title` | `hero_image`, `title`, `location` |
| 2 | Title + meta strip | `.property-header`, `.meta__acres`, `.meta__price`, `.meta__status` | `acres_label`, `price_label`, `status` |
| 3 | Sticky section nav | `.property-nav` anchors | `#facts`, `#map`, `#downloads`, `#details` (conditional) |
| 4 | Intro + broker(s) | `.property-intro`, `.property-intro__sidebar`, `.broker-card` (photo \| info side-by-side; two brokers side-by-side when `brokers.length > 1`) | `intro_paragraphs[]`, `brokers[]` (up to two in the editor UI; template allows more) |
| 4b | Executive assistance (optional) | `.executive-assistance` under sidebar | `executive_assistance[]` — strings; same text as a broker `name` (after trim) renders as `#broker-N` link |
| 5 | Photo gallery | `.property-overview-gallery` | `gallery_drive_url` (optional shared Drive folder/link), `gallery_images[]`. Drive **file** URLs in `src` are rewritten at build time for thumbnails (`build.py` filters). |
| 6 | Broker comment (optional) | `.property-comments` | `brokers_comment` |
| 7 | Overview & facts | `#facts`, `.property-facts__list` | `facts[]` |
| 8 | Map (optional) | `#map`, `.property-map__embed iframe` | `map_embed_url` |
| 9 | Downloads (optional) | `#downloads`, `.property-downloads__list` | `downloads[]` |
| 10 | Tabbed details | `#details`, `.tabbed-details` | `detail_tabs[]` |

## JSON file per property

- One file in `data/<slug>.json` (or any name; `slug` field controls output path).
- Build emits `dist/<slug>/index.html`.
- Shared branding lives in `data/site.json`.

## Optional / future fields

- `seo`: `meta_description`, `og_image`
- `nav`: override anchor labels
- `gallery_subtitle`: default “Full Photo Gallery”
- Multiple brokers: `brokers[]` array in template

## Webarchive → HTML (reference)

```bash
python3 scripts/inspect_webarchive.py ~/Downloads/the-wings-group.webarchive
# Writes /tmp/webarchive-main.html and prints plist summary
```
