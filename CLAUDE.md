# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

One-off tool, Mealime app shuts down soon. Two parts:

1. Share-sheet Shortcut that appends a recipe URL (`https://r.mealime.com/<id>`) to `iCloud Drive/mealime/urls.txt`. Deliberately not shipped as a binary (signed AEA archive, unreviewable, contains iCloud IDs; `*.shortcut` is gitignored). Documented in `SHORTCUT.md` (hand-build guide) and `shortcut/decoded.plist` (XML dump of the original, two iCloud IDs redacted). Keep the two in sync if the shortcut changes.
2. `mealime_export.py`: single-file, stdlib-only Python 3 script. Reads that URL list, writes markdown per recipe.

## Run

```bash
python3 mealime_export.py "$HOME/Library/Mobile Documents/com~apple~CloudDocs/mealime/urls.txt" [out_dir]
```

`out_dir` defaults to `./mealime-export`. No build, lint, or test setup exists.

## How the export works

- Each recipe page is a Next.js page. Recipe data is embedded JSON in `<script id="__NEXT_DATA__">`; the script reads `props.pageProps.publishedRecipe`. No HTML scraping beyond that regex. If Mealime changes the page shape, `extract()` is the only thing to fix.
- Output per recipe: `<slug>-<id>.md` (YAML frontmatter, Ingredients, Steps, Cookware, Nutrition) plus raw `json/<slug>-<id>.json` for fields the markdown drops, and `images/<slug>-<id>.<ext>` (from `presentation_image_url`, embedded in the markdown; skipped if already on disk).
- Field names used in `to_markdown()` are Mealime's own: `line_items[].quantity/ingredient_name`, `instructions[].primary_message/secondary_message` (secondary is that step's ingredient list, newline-separated `qty name` lines, not a tip), `cookwares[].name`, `serving_count`, `cooking_minutes`. Check the saved JSON before assuming a field exists.
- `fmt_nutrition()` renders flat dicts as bullets, anything nested as a JSON block.
- `app/` is the viewer web app (see `PLAN.md`). `server.py` is a stdlib http.server: `EXPORT_DIR=<out_dir> python3 app/server.py` then http://localhost:8080. Loads `json/*.json` at startup and enriches each line item with `pantry`, `key`, `category`, each step with `uses` (split `secondary_message`). Set `CERT_DIR` (dir with `fullchain.pem`/`privkey.pem`) for HTTPS, which the wake lock and service worker need off-localhost. `static/` is vanilla HTML/JS/CSS with hash routing (`#/`, `#/recipe/<id>`, `#/cook/<id>/<step>`, `#/plan/<id>`). Plan state (up to 5 recipe ids, last 10 plans as history) is a JSON blob the client owns; the server only stores it at `STATE_DIR/state.json` via `GET/PUT /api/state`. Service worker is network-first except images, so deploys land on next load, plus PWA bits (`manifest.json`, `sw.js`, icons). `Dockerfile` and `docker-compose.yml` build a read-only python:3.12-slim image; test with `docker build -t recipes app`. Note: macOS system python3 (LibreSSL 2.8) cannot serve ECDSA certs, the container can. `grocery.py` merges plan ingredients (`GET /api/grocery?ids=1,2`): sum only when normalized name and unit family match, show in the largest seen unit with amount >= 1, pantry items (no quantity) listed last; category overrides come from `state.overrides` (self-check: `python3 app/grocery.py <out_dir>`). `ingredients.py` parses quantity strings (self-check: `python3 app/ingredients.py <out_dir>`), `categories.json` maps normalized ingredient names to grocery aisles.
- Failures do not stop the run: failed URLs go to `<out_dir>/failed.txt`, which is valid input for a re-run.
- 1s sleep between requests, intentional. Keep it.
