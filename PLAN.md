# Recipe web app plan

Self-hosted replacement for the Mealime viewing experience, built on the 74 exported recipes (JSON + JPEG). Single Docker container on eyeball (decided 2026-10-21; Tank was the first draft), used from an iPad or phone in the kitchen.

## What the data actually contains

Checked against `recipes/json/*.json` on 2026-10-20. Mealime share pages now return 404, so this export is the whole corpus.

- 74 recipes, 982 ingredient lines, 934 steps. All recipes `units: US`.
- Per-step ingredients exist. `instructions[].secondary_message` is a newline-separated list of "quantity name" lines for that step (509 of 934 steps have one, 1180 lines total). This is the Mealime feature worth keeping. The current markdown exporter renders it as a sub-bullet "tip", which is wrong but harmless; the app reads the JSON, not the markdown.
- Per-step lines carry quantities even when the main list does not. 523 of 982 `line_items` have an empty `quantity`: these are pantry staples (salt, pepper, olive oil, soy sauce, dried spices, 41 distinct names). Their step lines say "½ tsp salt", "4 tsp extra virgin olive oil". So the main list is "what to buy", the step lines are "what to measure".
- Quantity strings use a small closed vocabulary. Tails after the number: lb, oz, fl oz, cup(s), pint, tbsp, tsp, ml, cloves, medium, small bunch(es), head(s), crown(s), sticks, slices, "(1 inch) pieces", and package forms "(N oz) pkg/can/block/bag/jar". Numbers use unicode vulgar fractions (½, ¼, ¾, ⅓). About 45 distinct patterns. A 40-line regex parser covers it; no NLP library needed.
- `cookwares[].name` is a clean list ("chef's knife", "stainless steel skillet", "garlic press (optional)").
- `nutrition` is a flat dict of ~75 keys (energy, carbs, fat, protein, fiber, sodium, plus amino acids and vitamins). Whether values are per serving or per recipe is not stated; check one recipe against the old app screenshot or a known value before showing it.

## What the research said (verified claims only)

Full report: `/private/tmp/claude-501/-Users-tim-REPOS-MealimeExtraction/4aca3cbc-0fa2-4f5b-92a8-6f1c57099ab4/tasks/w9n35iyqj.output`. 22 sources, 25 claims verified by 3-vote adversarial check, 4 refuted.

Build, do not adopt. Tandoor, Mealie, RecipeSage and KitchenOwl all do meal plan to shopping list, but none models per-step ingredient lists, RecipeSage's self-host is a six-service compose stack, and the claim that one of them could ingest this export via JSON-LD was refuted. With 74 recipes in clean JSON, the app is smaller than the import work.

Patterns to copy:

1. Cook mode (Mealime, Paprika). One step per screen in large type, prev/next, current-step highlight, checkable ingredients, screen held awake. Put the step's own ingredient sublist on that screen. Sources: support.mealime.com/article/88, paprikaapp.com.
2. Grocery merge rule (Paprika, Plan to Eat, RecipeSage). Sum only when normalised name matches and unit is the same or convertible within one dimension (volume to volume, mass to mass). Never convert volume to mass. When units differ, keep one header with the quantities side by side ("Mayonnaise: ¼ cup + 1 ½ tbsp"). Sources: learn.plantoeat.com, docs.recipesage.com.
3. Provenance. Under every merged line, show which recipe contributed what. Fall back to the raw string when parsing fails, never drop a line.
4. Aisle grouping (Plan to Eat, Tandoor). Each ingredient has one category (Produce, Meat, Dairy, Pantry, Frozen, Condiments, Other). Sort by category in a user-defined order, then name. Category comes from a per-ingredient override first, then a default table. Moving an item is sticky for that ingredient name forever.
5. Wake lock. `navigator.wakeLock` works in iOS Home Screen web apps from iOS 18.4 (WebKit bug 254545, fixed 2025-03). Re-request on `visibilitychange`, wrap in try/catch. Requires a secure context, so the app must be served over HTTPS.

Refuted or unverified: serving-size scaling UX (both Mela claims failed), "PWA needs HTTPS to install on LAN" (refuted as stated, but wake lock and service workers do need HTTPS regardless).

## Design

### Screens

- Index. Photo card grid, title, minutes, servings. Text filter. Tap a card to add to the plan or open the recipe. Plan tray at the bottom shows the chosen 1 to 5 recipes.
- Recipe. Photo hero, title, "35 min, 4 servings", Cookware chips, Ingredients (bought items with quantities, then a Pantry group), Steps as numbered cards with the step's ingredient lines rendered under the step text in a smaller monospace-ish block, exactly as Mealime did. Nutrition collapsed at the bottom. "Cook" button.
- Cook mode. Full screen, one step, large type, the step's ingredients beneath, big prev/next zones (tap left/right halves), progress "4 of 12", wake lock on, exit button.
- Plan. Tabs: one per recipe plus "Grocery". Recipe tabs show the recipe screen. Plan persists until replaced; keep a short history (last 10 plans) so a favourite week can be reloaded.
- Grocery. Grouped by category in configurable order. Each line: checkbox, merged quantity, name, expandable provenance. Pantry section last, unchecked by default, headed "Check you have". Long-press or a small menu moves a line to another category (sticky). "Copy as text" button for pasting into Reminders or AnyList.

### Architecture

One container, one process, no build step.

- Server: Python 3.12, stdlib only (`http.server`, `ssl`, `json`, `fractions`, `re`). Routes: `GET /` and static files, `GET /api/recipes` (index), `GET /api/recipes/<id>` (full JSON plus parsed ingredient lines), `GET/PUT /api/plan` (current plan and history), `GET /api/plan/grocery` (merged list), `PUT /api/overrides` (category overrides), `GET /images/<file>`. FastAPI only if the stdlib router gets annoying; it should not for seven routes.
- Client: `index.html`, `app.js`, `style.css`, `manifest.json`, `sw.js`. Hash routing (`#/recipe/2023`, `#/cook/2023`, `#/plan`, `#/grocery`). Vanilla JS, no framework. Service worker caches the shell, recipe JSON and images so the kitchen tablet still works while Tank reboots.
- Data at rest. The export directory mounted read-only is the source of truth: `json/*.json`, `images/*.jpg`. A second small volume holds `state.json`: `{plan: {recipe_ids, created}, history: [...], checked: {...}, overrides: {ingredient_name: category}}`. One file, rewritten atomically on each PUT. SQLite is not needed for one household.
- Startup. Server loads all 74 JSON files, parses every quantity string once into `(Fraction amount, unit, unit_family, package_size)`, normalises names, and keeps it in memory. Reload on SIGHUP or just restart the container when the export changes.
- Hand-maintained tables, two small JSON files in the repo: `categories.json` (ingredient name to category, with a few regex defaults such as `.*vinegar$` to Condiments) and `units.json` (unit aliases and families). About 250 distinct ingredient names; an hour of tagging.

### Grocery merge

For each recipe in the plan, for each `line_item` with a non-empty quantity:

1. Parse quantity: leading number (int, vulgar fraction, mixed), then unit tail. Package forms become `count=N, unit="pkg", size="5 oz"`.
2. Key = `(normalised name, unit family)`. Name normalisation: lowercase, drop text after a comma ("chicken breasts, boneless skinless" to "chicken breasts"), singularise the last word, apply a small synonym map.
3. Sum Fractions within a family after converting to the first-seen unit (tsp/tbsp/cup/fl oz/pint/ml are one family; oz/lb another; count-like units such as cloves, medium, head, bunch are each their own family so "2 medium onions" and "1 small bunch cilantro" never collide with anything they should not).
4. Different families for the same name stay separate lines under one header.
5. Render Fractions back as vulgar fractions. Keep the list of `(recipe name, raw string)` for provenance.

Pantry items (empty quantity): list once, no merge needed. Optional later: sum the per-step lines ("½ tsp salt" x 6) to show a rough total.

### TLS and hostname

Wake lock and service worker need HTTPS. certbot on chaos holds the `*.tainik.net` wildcard and Ansible pushes it to hosts; add eyeball to that play if it is not already there. Mount `fullchain.pem` and `privkey.pem` read-only into the container and wrap the stdlib server with `ssl.SSLContext`. Add `recipes.tainik.net` to local DNS pointing at eyeball (192.168.0.222). No reverse proxy needed.

### Docker

```
FROM python:3.12-slim
WORKDIR /app
COPY app/ .
USER 1000
EXPOSE 8443
CMD ["python", "server.py"]
```

Compose at `/etc/docker/containers/recipes/docker-compose.yml` on eyeball (same layout Tank uses); confirm Docker is installed there first. Mounts: three bind mounts (export read-only, state read-write, certs read-only), `read_only: true`, `restart: unless-stopped`, port 8443.

## Phases

Status 2026-10-21: all phases built. Nutrition confirmed per serving; serving scaler deliberately skipped.

0. Parser and tables (half a day). `parse_quantity()` with a test that runs it over all 982 lines and asserts zero unparsed. Write `categories.json`. Fix the markdown exporter so `secondary_message` renders as "uses:" lines, not a tip.
1. Recipe display (one day). Server with static files and the recipe routes. Index grid, recipe page with per-step ingredients, cookware, pantry group. This alone replaces most of what was lost.
2. Cook mode and PWA (half a day). Single-step view, wake lock, manifest, service worker, TLS, DNS. Install on the kitchen iPad.
3. Meal plan (half a day). Pick 1 to 5, tabbed view, persisted plan and history.
4. Grocery list (one day). Merge, categories, sticky overrides, checkboxes, copy as text.
5. Optional. Nutrition panel once per-serving vs per-recipe is confirmed. Pantry totals from step lines. Serving scaler is skipped: Mealime recipes are fixed-serving and no verified UX pattern exists for it.

## Wish list (2026-10-21, after v1.0)

6. Ingredient library. `state.locations {key: place}` and `state.places [...]`, page at `#/library` listing every ingredient key (`GET /api/ingredients`) with a location select, unassigned first. Recipe Ingredients tab gets a persisted "By location" toggle that groups bought and pantry items by place, unset ones last with an inline select. Done 2026-10-21.
7. Grocery list to TickTick. App calls the TickTick Open API (OAuth2 once from the Mac, token file beside state.json), "Send to TickTick" on the grocery tab posts one task per unchecked item into the chosen list. Built 2026-10-21 (`app/ticktick.py`, `POST /api/ticktick`, button on the grocery tab). Tested live 2026-10-21: TickTick issued a plain API key (no OAuth app needed; the OAuth helper was removed), it works as a Bearer token from `/etc/docker/containers/recipes/state/ticktick.json`. Tasks land in the list's aisle columns via `columnId`, which the create endpoint honors although the docs don't list it; column ids come from `GET /project/{id}/data`.
8. Add recipe from URL. Server fetches the page, reads schema.org Recipe JSON-LD (name, image, ingredients, instructions, yield, time, nutrition), then one Claude call (Haiku) assigns ingredients to steps, lists cookware, and picks aisle categories for new names. Saved as Mealime-shaped JSON plus image under `STATE_DIR/recipes/`, loaded alongside the export. Works without the key (no per-step lists). `ANTHROPIC_API_KEY` via `env_file: .env` next to the compose file. Built 2026-10-21. Found: Allrecipes, Serious Eats, Simply Recipes, Budget Bytes return 403 to any non-browser TLS fingerprint (curl too), King Arthur works. So the route also accepts `html` in the body for a Safari share-sheet Shortcut (Get Contents of URL, then POST `{url, html}`); the AI pass is untested until a key is on eyeball.

## Open items

- Confirm whether `nutrition` values are per serving or per recipe before showing them.
- Decide hostname (`recipes.tainik.net` assumed) and whether the app gets its own repo or lives under `app/` here. Own repo is cleaner; this repo is the one-off exporter.
- iOS version on the kitchen device must be 18.4 or later for wake lock from the Home Screen; older iPads can still use it in a Safari tab.
