"""Send grocery items to a TickTick list via the Open API (stdlib only).

One-time auth from a machine with a browser:
    python3 app/ticktick.py auth <client_id> <client_secret> <token_file>
Register the app at developer.ticktick.com with redirect URI http://localhost:8765/callback.
Copy the token file to STATE_DIR/ticktick.json on the server (chmod 600). Set TICKTICK_LIST
to the list name. Access tokens last months and the Open API has no refresh; re-run auth
when sends start failing with 401.
"""
import base64
import json
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

API = "https://api.ticktick.com/open/v1"
REDIRECT = "http://localhost:8765/callback"
SCOPE = "tasks:write tasks:read"


def _call(token, method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read() or b"null")


def project_id(token, name):
    for p in _call(token, "GET", "/project"):
        if p.get("name", "").lower() == name.lower():
            return p["id"]
    raise ValueError(f"no TickTick list named {name!r}")


def add_tasks(token, list_name, items):
    """items: [{"title": "6 tbsp soy sauce", "content": "Condiments · 2 recipes"}]. Returns count."""
    pid = project_id(token, list_name)
    for it in items:  # ponytail: one POST per item, the Open API has no batch create
        _call(token, "POST", "/task", {"projectId": pid, "title": it["title"], "content": it.get("content", "")})
    return len(items)


def auth(client_id, secret, out):
    url = "https://ticktick.com/oauth/authorize?" + urllib.parse.urlencode(
        {"scope": SCOPE, "client_id": client_id, "state": "recipes", "redirect_uri": REDIRECT, "response_type": "code"})
    print("Open this in a browser and approve:\n\n  " + url + "\n")
    code = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            code["v"] = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("code", [""])[0]
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok, back to the terminal")
        log_message = lambda *a: None  # noqa: E731

    srv = HTTPServer(("localhost", 8765), H)
    while not code.get("v"):
        srv.handle_request()
    data = urllib.parse.urlencode({"code": code["v"], "grant_type": "authorization_code", "scope": SCOPE, "redirect_uri": REDIRECT}).encode()
    basic = base64.b64encode(":".join([client_id, secret]).encode()).decode()  # client auth is the Basic header
    req = urllib.request.Request("https://ticktick.com/oauth/token", data=data, headers={
        "Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        tok = json.loads(r.read())
    Path(out).write_text(json.dumps({"access_token": tok["access_token"]}))
    Path(out).chmod(0o600)
    print(f"token written to {out}; lists visible:", [p["name"] for p in _call(tok["access_token"], "GET", "/project")])


if __name__ == "__main__":
    if sys.argv[1:2] == ["auth"] and len(sys.argv) == 5:
        auth(*sys.argv[2:])
    else:
        print(__doc__)
