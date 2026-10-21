#!/usr/bin/env python3
"""Export Mealime recipes from share URLs to markdown.

Usage:
    python3 mealime_export.py urls.txt [out_dir]

urls.txt: one URL per line (https://r.mealime.com/9885). Blank lines and
lines starting with # are skipped.

Each page embeds the full recipe in <script id="__NEXT_DATA__">. This reads
props.pageProps.publishedRecipe and writes one .md per recipe, plus the raw
JSON in out_dir/json/ in case you want fields the markdown leaves out, and the
main photo in out_dir/images/ (embedded in the .md).
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/605.1.15"
NEXT_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.geturl(), r.read().decode("utf-8", "replace")


def extract(html):
    m = NEXT_RE.search(html)
    if not m:
        raise ValueError("no __NEXT_DATA__ block")
    data = json.loads(m.group(1))
    return data["props"]["pageProps"]["publishedRecipe"]


def save_image(r, out, stem):
    """Download the main recipe photo. Returns path relative to out, or None."""
    url = r.get("presentation_image_url") or r.get("thumbnail_image_url")
    if not url:
        return None
    rel = Path("images") / (stem + (Path(urlparse(url).path).suffix or ".jpg"))
    dest = out / rel
    if not dest.exists():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest.write_bytes(resp.read())
    return rel.as_posix()


def fmt_nutrition(n):
    if not n:
        return ""
    if isinstance(n, dict):
        flat = all(not isinstance(v, (dict, list)) for v in n.values())
        if flat:
            return "\n".join(f"- {k}: {v}" for k, v in n.items())
    return "```json\n" + json.dumps(n, indent=2) + "\n```"


def to_markdown(r, source_url, final_url, image=None):
    lines = [
        "---",
        f'title: "{r["name"].replace(chr(34), chr(39))}"',
        f"source: {source_url}",
        f"canonical: {final_url}",
        f"mealime_id: {r.get('id')}",
        f"servings: {r.get('serving_count')}",
        f"minutes: {r.get('cooking_minutes')}",
        f"units: {r.get('units')}",
        f"image: {image}" if image else "image:",
        "tags: [recipe, mealime]",
        "---",
        "",
        f"# {r['name']}",
        "",
    ]
    if image:
        lines += [f"![{r['name']}]({image})", ""]
    lines += [
        f"{r.get('cooking_minutes')} minutes, {r.get('serving_count')} servings",
        "",
        "## Ingredients",
        "",
    ]
    for li in r.get("line_items", []):
        q = (li.get("quantity") or "").strip()
        lines.append(f"- {q + ' ' if q else ''}{li.get('ingredient_name', '')}")
    lines += ["", "## Steps", ""]
    for i, step in enumerate(r.get("instructions", []), 1):
        text = (step.get("primary_message") or "").strip()
        sec = (step.get("secondary_message") or "").strip()
        lines.append(f"{i}. {text}")
        if sec:
            lines.append(f"   - {sec}")
    cw = [c["name"] for c in r.get("cookwares", [])]
    if cw:
        lines += ["", "## Cookware", ""] + [f"- {c}" for c in cw]
    nut = fmt_nutrition(r.get("nutrition"))
    if nut:
        lines += ["", "## Nutrition", "", nut]
    lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    urls_file = Path(sys.argv[1])
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "mealime-export")
    (out / "json").mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)

    urls, seen = [], set()
    for line in urls_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line not in seen:
            seen.add(line)
            urls.append(line)

    failed = []
    for n, url in enumerate(urls, 1):
        try:
            final, html = fetch(url)
            r = extract(html)
            stem = re.sub(r"[^\w.-]", "_", f"{r['slug']}-{r['id']}")  # slug is remote input
            (out / "json" / f"{stem}.json").write_text(json.dumps(r, indent=2))
            image = save_image(r, out, stem)
            (out / f"{stem}.md").write_text(to_markdown(r, url, final, image))
            print(f"[{n}/{len(urls)}] ok   {stem}")
        except Exception as e:  # keep going, report at the end
            print(f"[{n}/{len(urls)}] FAIL {url}: {e}")
            failed.append(url)
        time.sleep(1)

    if failed:
        (out / "failed.txt").write_text("\n".join(failed) + "\n")
        print(f"\n{len(failed)} failed, listed in {out / 'failed.txt'}")


if __name__ == "__main__":
    main()
