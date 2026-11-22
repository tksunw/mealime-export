#!/usr/bin/env python3
"""Bulk-import recipe files (pdf, png/jpg, txt) into the running app.

    python3 app/import_files.py https://recipes.tainik.net:8443 file...

POSTs each file to /api/import and waits between files so the background Claude
passes on the server do not pile up. Failures are printed and skipped.
"""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def main(server: str, files: list[str]) -> int:
    failed = 0
    for p in map(Path, files):
        ext = p.suffix.lower()
        if ext == ".pdf":
            body = {"pdf": base64.b64encode(p.read_bytes()).decode()}
        elif ext in MEDIA:
            body = {"image": base64.b64encode(p.read_bytes()).decode(), "media_type": MEDIA[ext]}
        elif ext in (".txt", ".md"):
            body = {"text": p.read_text(encoding="utf-8-sig")}
        else:
            print(f"skip {p.name}")
            continue
        body["name"] = p.stem
        req = urllib.request.Request(f"{server.rstrip('/')}/api/import", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                r = json.loads(resp.read())
            print(f"ok   {p.name} -> {r['id']} {r['name']}")
        except urllib.error.HTTPError as e:
            failed += 1
            print(f"FAIL {p.name}: {e.read().decode(errors='replace')[:300]}")
        except Exception as e:
            failed += 1
            print(f"FAIL {p.name}: {e}")
        time.sleep(15)  # ponytail: enrich runs server-side in a thread per import; keep them from stacking
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2:]))
