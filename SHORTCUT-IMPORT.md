# Build the import shortcut yourself

Share a recipe page from Safari and it lands in the recipe app. Needed because most big recipe sites (Allrecipes, Serious Eats, Simply Recipes, Budget Bytes) return 403 to anything that is not a real browser, so the server cannot fetch them itself. The Shortcut fetches the page with iOS networking and hands the HTML to `POST /api/import`.

Two ways to get it. Easiest: generate and sign it on a Mac, then open the file on the iPad from Files (it imports into Shortcuts):

```
python3 shortcut/build_import_shortcut.py unsigned.shortcut
shortcuts sign --mode anyone --input unsigned.shortcut --output "Add recipe.shortcut"
```

The builder is plain Python writing the plist, so it is reviewable and contains no iCloud ids. The hand-build steps below describe the same five-action shortcut; the Shortcuts editor changes between releases, so action names may differ a little from what is written here. Action identifiers are given so the steps are unambiguous.

## Steps

In the Shortcuts app, create a new shortcut named `Add recipe`.

Shortcut settings (the "i" button):

- Turn on **Show in Share Sheet**.
- Receive: **URLs** and **Safari web pages**. Untick the rest.
- If there is no input: **Ask for** URL. Lets the same shortcut run from the Shortcuts app by pasting a link.

Action 1: **Get URLs from Input** (`is.workflow.actions.detect.link`)

- Input: **Shortcut Input**.
- Turns a Safari web page item into a plain URL. Rename the output variable to `Page URL` (tap the result pill, Rename).

Action 2: **Get Contents of URL** (`is.workflow.actions.downloadurl`)

- URL: `Page URL`.
- Method: GET. No headers needed.
- This is the browser-side fetch. Rename the output to `Page HTML`.

Action 3: **Get Text from Input** (`is.workflow.actions.detect.text`)

- Input: `Page HTML`.
- Makes sure the page is passed as text, not a file. Rename the output to `HTML text`.

Action 4: **Get Contents of URL** (`is.workflow.actions.downloadurl`)

- URL: `https://recipes.tainik.net:8443/api/import`
- Method: **POST**.
- Request Body: **JSON**. Add two fields:
  - `url` (Text): `Page URL`
  - `html` (Text): `HTML text`
- Rename the output to `Result`.

Action 5: **Show Notification** (`is.workflow.actions.notification`)

- Title: `Add recipe`. Body: `Result`.
- The server replies with the recipe id and name on success, or an `error` message. Both show as-is. Open the app to see the new recipe at the top of the index (sorted by name, so use the filter).

## Use

On any recipe page in Safari: Share, **Add recipe**. A notification shows the server's reply. Open the app; the new recipe is in the index.

With `ANTHROPIC_API_KEY` set on the server the import takes 10 to 30 seconds (one Claude call fills the per-step ingredient lists, cookware and aisles). Without it, a second or two and no per-step lists. Shortcuts gives up on a request after about 60 seconds; if that ever trips, the recipe is still saved and shows on the next index load.

## What it does not do

Two network calls: GET the shared page, POST to `recipes.tainik.net`. No files written, no other hosts. The page HTML is sent only to your own server. Sites that block even iOS fetches (rare) fail at action 2 with an HTTP error; the server's direct fetch would have failed on those too.
