"""Send grocery items to a TickTick list via the Open API (stdlib only).

Auth: TickTick issues a plain API key; put it in STATE_DIR/ticktick.json as
{"access_token": "<key>"} (chmod 600). It goes out as a Bearer token. Set TICKTICK_LIST
to the list name; emoji and case are ignored when matching. Optional "columns" dict in
the same file overrides the aisle -> column map below.

Self-check: python3 app/ticktick.py
"""
import json
import re
import urllib.request

API = "https://api.ticktick.com/open/v1"


def _call(token, method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read() or b"null")


def _plain(name):  # "🥚Grocery List" -> "grocery list": emoji and case don't count
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def project_id(token, name):
    for p in _call(token, "GET", "/project"):
        if _plain(p.get("name", "")) == _plain(name):
            return p["id"]
    raise ValueError(f"no TickTick list named {name!r}")


# app aisle -> TickTick column (section) name; override with a "columns" dict in the token file
COLUMNS = {"Produce": "Fruit and Veggies", "Meat & Seafood": "Meat", "Dairy & Eggs": "Dairy & Deli", "Deli": "Dairy & Deli", "Bakery": "Bakery",
           "Frozen": "Frozen", "Grains & Pasta": "Aisles", "Canned & Jarred": "Aisles", "Condiments & Sauces": "Aisles",
           "Pantry & Spices": "Aisles", "Pantry": "Aisles", "Other": "Aisles"}


def add_tasks(token, list_name, items, columns=None):
    """items: [{"title": "6 tbsp soy sauce", "content": "Condiments · 2 recipes", "category": "Produce"}]. Returns count."""
    pid = project_id(token, list_name)
    cols = {_plain(c["name"]): c["id"] for c in (_call(token, "GET", f"/project/{pid}/data") or {}).get("columns") or []}
    colmap = {**COLUMNS, **(columns or {})}
    for it in items:  # ponytail: one POST per item, the Open API has no batch create
        body = {"projectId": pid, "title": it["title"], "content": it.get("content", "")}
        col = cols.get(_plain(colmap.get(it.get("category", ""), "")))
        if col:
            body["columnId"] = col
        _call(token, "POST", "/task", body)
    return len(items)


if __name__ == "__main__":
    assert _plain("🥚Grocery List") == _plain("grocery list") == "grocery list"
    print("ok")
