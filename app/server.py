#!/usr/bin/env python3
"""Recipe viewer server. Stdlib only.

    EXPORT_DIR=/path/to/export python3 app/server.py

Env: EXPORT_DIR (has json/ and images/), PORT (default 8080),
CERT_DIR (optional; if it holds fullchain.pem and privkey.pem, serves HTTPS).
Loads every json/*.json at startup; restart to pick up new recipes.
"""
import json
import mimetypes
import os
import ssl
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ingredients import normalize_name, parse_line  # noqa: E402

HERE = Path(__file__).parent
STATIC = HERE / "static"
EXPORT = Path(os.environ.get("EXPORT_DIR", "mealime-export"))
CATEGORIES = json.loads((HERE / "categories.json").read_text())


def load_recipes():
    recipes = {}
    for f in sorted((EXPORT / "json").glob("*.json")):
        r = json.loads(f.read_text())
        img = next((p.name for p in (EXPORT / "images").glob(f.stem + ".*")), None)
        r["image"] = f"/images/{img}" if img else None
        for li in r["line_items"]:
            li["pantry"] = not (li.get("quantity") or "").strip()
            li["key"] = normalize_name(li["ingredient_name"])
            li["category"] = CATEGORIES["ingredients"].get(li["key"], "Other")
        for st in r["instructions"]:
            st["uses"] = [l.strip() for l in (st.get("secondary_message") or "").splitlines() if l.strip()]
        recipes[r["id"]] = r
    return recipes


RECIPES = load_recipes()
INDEX = [
    {"id": r["id"], "name": r["name"], "slug": r["slug"], "minutes": r.get("cooking_minutes"),
     "servings": r.get("serving_count"), "image": r["image"]}
    for r in sorted(RECIPES.values(), key=lambda r: r["name"].lower())
]


class Handler(SimpleHTTPRequestHandler):
    do_HEAD = lambda self: self.do_GET()  # noqa: E731

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/recipes":
            return self.send_json(INDEX)
        if path.startswith("/api/recipes/"):
            r = RECIPES.get(int(path.rsplit("/", 1)[1])) if path.rsplit("/", 1)[1].isdigit() else None
            return self.send_json(r) if r else self.send_error(HTTPStatus.NOT_FOUND)
        if path.startswith("/images/"):
            return self.send_file(EXPORT / "images" / Path(path).name, cache=86400 * 30)
        if path == "/":
            path = "/index.html"
        return self.send_file(STATIC / Path(path).name)

    def send_json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_file(self, p: Path, cache=0):
        if not p.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        body = p.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", f"max-age={cache}" if cache else "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def main():
    port = int(os.environ.get("PORT", 8080))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    cert = Path(os.environ.get("CERT_DIR", "")) if os.environ.get("CERT_DIR") else None
    if cert and (cert / "fullchain.pem").is_file():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert / "fullchain.pem", cert / "privkey.pem")
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    scheme = "https" if cert and (cert / "fullchain.pem").is_file() else "http"
    print(f"{len(RECIPES)} recipes from {EXPORT}, {scheme}://0.0.0.0:{port}", file=sys.stderr)
    srv.serve_forever()


if __name__ == "__main__":
    main()
