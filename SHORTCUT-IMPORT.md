# Build the import shortcut yourself

Share a recipe page from Safari and it lands in the recipe app. Needed because most big recipe sites (Allrecipes, Serious Eats, Simply Recipes, Budget Bytes) return 403 to anything that is not a real browser, so the server cannot fetch them itself. The Shortcut fetches the page with iOS networking and hands the HTML to `POST /api/import`.

Six actions, about five minutes. Built by hand for the same reason as `SHORTCUT.md`: no binary to trust. Action identifiers are given so the steps are unambiguous.

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

Action 5: **Get Dictionary Value** (`is.workflow.actions.getvalueforkey`)

- Get **Value** for `id` in `Result`.
- Rename the output to `Recipe ID`.

Action 6: **If** (`is.workflow.actions.conditional`)

- Condition: `Recipe ID` **has any value**.
- Inside If: **Open URLs** (`is.workflow.actions.openurl`) with `https://recipes.tainik.net:8443/#/recipe/` followed by the `Recipe ID` variable. Opens the new recipe in the app.
- Inside Otherwise: **Get Dictionary Value** for `error` in `Result`, then **Show Notification** (`is.workflow.actions.notification`) with that value as the body. The server's message says what went wrong, usually "no schema.org Recipe JSON-LD on that page".

## Use

On any recipe page in Safari: Share, **Add recipe**. The app opens on the imported recipe. On the iPad the Home Screen app is a separate Safari context, so the Open URLs step lands in Safari, not the installed app; switch to the app and pull the index to see it.

With `ANTHROPIC_API_KEY` set on the server the import takes 10 to 30 seconds (one Claude call fills the per-step ingredient lists, cookware and aisles). Without it, a second or two and no per-step lists. Shortcuts gives up on a request after about 60 seconds; if that ever trips, the recipe is still saved and shows on the next index load.

## What it does not do

Two network calls: GET the shared page, POST to `recipes.tainik.net`. No files written, no other hosts. The page HTML is sent only to your own server. Sites that block even iOS fetches (rare) fail at action 2 with an HTTP error; the server's direct fetch would have failed on those too.
