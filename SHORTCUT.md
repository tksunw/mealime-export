# Build the shortcut yourself

Two actions. Building it by hand takes about two minutes and means there is no opaque binary to trust. Everything below comes from `shortcut/decoded.plist`; the action identifiers are listed so you can grep for each one.

## Steps

In the Shortcuts app, create a new shortcut named `Append to Mealime URLs`.

Shortcut settings (the "i" button):

- Turn on **Show in Share Sheet**. Accepted input types can stay at the default (`WFWorkflowInputContentItemClasses` lists all of them; only URLs and text matter here).
- Matches `WFWorkflowTypes`: `ActionExtension`, `WFWorkflowTypeShowInSearch`.

Action 1: **Append to Text File** (`is.workflow.actions.file.append`)

- Input: **Shortcut Input** (`ExtensionInput` in the plist). This is the URL passed by the share sheet.
- File: iCloud Drive folder `mealime`, file path `urls.txt`.
- Make New Line: leave at the default (on). The plist omits the parameter, so the app default applies. This is what puts one URL per line, which is the format `mealime_export.py` expects.

Action 2: **Show Notification** (`is.workflow.actions.notification`)

- Title/body: `Saved`.

Create the `mealime` folder in iCloud Drive first if it does not exist.

## Use

In the Mealime app, share a recipe, pick the shortcut. The share URL (`https://r.mealime.com/<id>`) is appended to `iCloud Drive/mealime/urls.txt`.

## What it does not do

No network calls, no other files touched, no variables beyond the shortcut input. The only paths referenced are `mealime/urls.txt` in iCloud Drive.
