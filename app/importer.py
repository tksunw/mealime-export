"""Import a recipe from a web page into the Mealime JSON shape the app reads.

Path: fetch page -> schema.org Recipe JSON-LD -> Mealime-shaped dict -> optional
Claude pass (per-step ingredient lines, cookware, aisle categories) -> json + image
+ markdown under <dest>/. Stdlib only; Claude via urllib against the Messages API.

Self-check: python3 app/importer.py            (fixture, no network)
Manual:     python3 app/importer.py <url> <dest_dir>
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from ingredients import parse_line  # noqa: E402

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
LD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
MAX_BYTES = 5 * 1024 * 1024
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")

# web unit words -> Mealime vocabulary
_UNIT_WORDS = [
    (r"tablespoons?|tbsps?\.?|tbl\.?", "tbsp"), (r"teaspoons?|tsps?\.?", "tsp"),
    (r"pounds?|lbs?\.?", "lb"), (r"ounces?|oz\.?", "oz"), (r"fluid oz|fl\.? ?oz\.?", "fl oz"),
    (r"cups?", "cup"), (r"pints?", "pint"), (r"cloves?", "cloves"), (r"grams?|g", "g"),
    (r"kilograms?|kg", "kg"), (r"milliliters?|millilitres?|ml", "ml"), (r"liters?|litres?|l", "l"),
]
_DEC = {"5": "½", "25": "¼", "75": "¾", "33": "⅓", "67": "⅔", "125": "⅛"}
_ASCII_FRAC = {"1/2": "½", "1/4": "¼", "3/4": "¾", "1/3": "⅓", "2/3": "⅔", "1/8": "⅛"}


def fetch(url: str) -> str:
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("url must be http(s)")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(MAX_BYTES).decode("utf-8", "replace")


def find_recipe(html: str) -> dict:
    """First schema.org Recipe object in any ld+json block (handles @graph and lists)."""
    def walk(o):
        if isinstance(o, dict):
            t = o.get("@type")
            if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
                return o
            for v in o.values():
                if (r := walk(v)):
                    return r
        elif isinstance(o, list):
            for v in o:
                if (r := walk(v)):
                    return r
    for m in LD_RE.finditer(html):
        try:
            if (r := walk(json.loads(m.group(1).strip()))):
                return r
        except ValueError:
            continue
    raise ValueError("no schema.org Recipe JSON-LD on that page")


def _text(o) -> str:
    if isinstance(o, dict):
        return _text(o.get("text") or o.get("name") or "")
    if isinstance(o, list):
        return " ".join(_text(x) for x in o)
    return _html.unescape(re.sub(r"<[^>]+>", "", str(o or ""))).strip()


def steps_of(ri) -> list:
    """recipeInstructions: string, [string], [HowToStep], or [HowToSection{itemListElement}]."""
    if isinstance(ri, str):
        parts = [p.strip() for p in re.split(r"\n+|(?<=\.)\s+(?=\d+\.\s)", ri) if p.strip()]
        return parts or [ri]
    out = []
    for s in ri or []:
        if isinstance(s, dict) and s.get("@type") == "HowToSection":
            out += steps_of(s.get("itemListElement"))
        else:
            out.append(_text(s))
    return [s for s in out if s]


def split_ingredient(text: str):
    """'2 tablespoons soy sauce' -> ('2 tbsp', 'soy sauce'); unparsed -> ('', text)."""
    s = re.sub(r"\s+", " ", _text(text)).strip()
    for a, b in _ASCII_FRAC.items():
        s = re.sub(rf"(?<![\d/]){re.escape(a)}(?![\d/])", b, s)
    s = re.sub(r"^(\d+)?\.(\d+)", lambda m: (m.group(1) or "").lstrip("0") + " " + _DEC.get(m.group(2), "." + m.group(2)) if m.group(2) in _DEC else m.group(0), s).strip()  # "0.25" -> "¼", "1.5" -> "1 ½"
    s = re.sub(r"^(\d+) ?([½¼¾⅓⅔⅛])", r"\1 \2", s)  # "1½" -> "1 ½"
    s = re.sub(r"^([\d½¼¾⅓⅔⅛]+(?: [½¼¾⅓⅔⅛])?)\s*(?:-|–|to)\s*[\d½¼¾⅓⅔⅛]+(?: [½¼¾⅓⅔⅛])?", r"\1", s)  # "2-3 cloves", "½ to ⅔ cup" -> low end
    m = re.match(r"^([\d½¼¾⅓⅔⅛][\d½¼¾⅓⅔⅛ ./]*?)\s+([A-Za-z.]+(?: oz\.?)?)(?=\s|$)", s)
    if m:
        for pat, canon in _UNIT_WORDS:
            if re.fullmatch(pat, m.group(2), re.I):
                s = f"{m.group(1)} {canon}{s[m.end():]}"
                break
    s = re.sub(r"\s+of\s+", " ", s, count=1) if re.match(r"^[\d½¼¾⅓⅔⅛][^,]*?\s+of\s+", s) else s
    q, rest = parse_line(s)
    if q is None or not rest:
        return "", re.sub(r",?\s*to taste$", "", s, flags=re.I)
    return s[: len(s) - len(rest)].strip(), rest


def minutes_of(ld) -> int | None:
    def iso(d):
        if not isinstance(d, str):
            return 0
        h = re.search(r"(\d+)H", d)
        m = re.search(r"(\d+)M", d)
        return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)
    total = iso(ld.get("totalTime")) or iso(ld.get("prepTime")) + iso(ld.get("cookTime"))
    return total or None


def servings_of(ld) -> int | None:
    y = ld.get("recipeYield")
    y = y[0] if isinstance(y, list) and y else y
    m = re.search(r"\d+", str(y or ""))
    return int(m.group()) if m else None


def image_of(ld) -> str | None:
    i = ld.get("image")
    if isinstance(i, list):
        i = i[0] if i else None
    if isinstance(i, dict):
        i = i.get("url") or i.get("contentUrl")
    return i if isinstance(i, str) and i.startswith("http") else None


_NUT = {"calories": ("energy", 1), "proteinContent": ("protein", 1), "carbohydrateContent": ("carbs", 1),
        "fatContent": ("fat", 1), "fiberContent": ("fiber", 1), "sugarContent": ("sugars", 1),
        "saturatedFatContent": ("saturated", 1), "sodiumContent": ("sodium", 1000),
        "cholesterolContent": ("cholesterol", 1000)}


def nutrition_of(ld) -> dict:
    """Mealime keys, per serving as sites report it. Minerals in mg (g values scaled)."""
    n = ld.get("nutrition") or {}
    out = {}
    for k, (key, g_to_mg) in _NUT.items():
        m = re.match(r"\s*([\d.]+)\s*(k?cal|mg|g)?", str(n.get(k) or ""), re.I)
        if m:
            v = float(m.group(1))
            if g_to_mg > 1 and (m.group(2) or "").lower() == "g":
                v *= g_to_mg
            out[key] = v
    return out


def to_mealime(ld: dict, rid: int, url: str) -> dict:
    name = _text(ld.get("name")) or "Untitled"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
    line_items = []
    for i, ing in enumerate(ld.get("recipeIngredient") or ld.get("ingredients") or []):
        q, n = split_ingredient(ing)
        line_items.append({"id": i + 1, "quantity": q, "ingredient_name": n})
    return {
        "id": rid, "recipe_id": rid, "name": name, "slug": slug, "units": "US", "source_url": url,
        "serving_count": servings_of(ld), "cooking_minutes": minutes_of(ld),
        "line_items": line_items,
        "instructions": [{"id": i + 1, "primary_message": s, "secondary_message": ""} for i, s in enumerate(steps_of(ld.get("recipeInstructions")))],
        "cookwares": [], "nutrition": nutrition_of(ld), "presentation_image_url": image_of(ld),
    }


def enrich(r: dict, aisles: list) -> dict:
    """One Claude call: per-step ingredient lines, cookware, aisle per ingredient. No key -> unchanged."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return r
    ings = "\n".join(f"{li['quantity']} {li['ingredient_name']}".strip() for li in r["line_items"])
    steps = "\n".join(f"{s['id']}. {s['primary_message']}" for s in r["instructions"])
    prompt = f"""Recipe: {r['name']}

Ingredients:
{ings}

Steps:
{steps}

Return JSON only, no prose, shape:
{{"steps": {{"<step id>": ["<qty> <ingredient>", ...]}}, "cookwares": ["<tool>", ...], "categories": {{"<ingredient name as written>": "<aisle>"}}}}

Rules: "steps" lists the ingredients used in each step with the amount used in that step (split an ingredient across steps if the recipe does; omit steps that use none). Write amounts with unicode fractions and short units (tsp, tbsp, cup, oz, lb). "cookwares" is the kitchen equipment needed (pans, bowls, knife, etc.). "categories" maps every ingredient to one of: {", ".join(aisles)}."""
    body = json.dumps({"model": MODEL, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        text = "".join(b.get("text", "") for b in json.loads(resp.read())["content"])
    data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    for s in r["instructions"]:
        lines = data.get("steps", {}).get(str(s["id"])) or []
        s["secondary_message"] = "\n".join(str(x) for x in lines)
    r["cookwares"] = [{"id": i + 1, "name": str(c), "slug": re.sub(r"\W+", "-", str(c).lower())} for i, c in enumerate(data.get("cookwares") or [])]
    r["_categories"] = {str(k): v for k, v in (data.get("categories") or {}).items() if v in aisles}
    return r


def import_url(url: str, dest: Path, rid: int, aisles: list, html: str | None = None) -> dict:
    """Fetch (or take the page html from a browser-side fetch, since many recipe sites 403
    non-browser TLS fingerprints), convert, enrich, save json/image/markdown under dest."""
    r = enrich(to_mealime(find_recipe(html or fetch(url)), rid, url), aisles)
    stem = f"{r['slug']}-{rid}"
    (dest / "json").mkdir(parents=True, exist_ok=True)
    (dest / "images").mkdir(exist_ok=True)
    image = None
    if r.get("presentation_image_url"):
        try:
            img = urllib.request.urlopen(urllib.request.Request(r["presentation_image_url"], headers={"User-Agent": UA}), timeout=20)
            ext = Path(urlparse(r["presentation_image_url"]).path).suffix.lower() or ".jpg"
            ext = ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
            (dest / "images" / (stem + ext)).write_bytes(img.read(MAX_BYTES))
            image = f"images/{stem}{ext}"
        except Exception:  # ponytail: no photo is fine
            pass
    (dest / "json" / f"{stem}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False))
    try:
        from mealime_export import to_markdown
        (dest / f"{stem}.md").write_text(to_markdown(r, url, url, image).replace("tags: [recipe, mealime]", "tags: [recipe, imported]"))
    except ImportError:  # ponytail: md is a nicety; the app reads the json
        pass
    return r


def _selfcheck():
    html = """<html><script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"WebPage"},
    {"@type":["Recipe"],"name":"Test Stir Fry","image":{"@type":"ImageObject","url":"https://x.test/a.jpg"},
    "recipeYield":["4","4 servings"],"totalTime":"PT35M","nutrition":{"@type":"NutritionInformation","calories":"420 kcal","sodiumContent":"0.8 g","proteinContent":"30 g"},
    "recipeIngredient":["2 tablespoons soy sauce","0.25 cup olive oil","1.5 tsp cumin","1/2 to 2/3 cup hot water","1 1/2 pounds chicken thighs, boneless","3 cloves garlic, minced","1&frac12; cups of rice","salt to taste","2-3 green onions","100 g snap peas"],
    "recipeInstructions":[{"@type":"HowToSection","name":"Prep","itemListElement":[{"@type":"HowToStep","text":"Mince the garlic."}]},{"@type":"HowToStep","text":"Cook the <b>chicken</b>."}]}]}</script></html>"""
    ld = find_recipe(html)
    r = to_mealime(ld, 1000001, "https://x.test/r")
    got = [(li["quantity"], li["ingredient_name"]) for li in r["line_items"]]
    assert got == [("2 tbsp", "soy sauce"), ("¼ cup", "olive oil"), ("1 ½ tsp", "cumin"), ("½ cup", "hot water"), ("1 ½ lb", "chicken thighs, boneless"), ("3 cloves", "garlic, minced"),
                   ("1 ½ cup", "rice"), ("", "salt"), ("2", "green onions"), ("100 g", "snap peas")], got
    assert [s["primary_message"] for s in r["instructions"]] == ["Mince the garlic.", "Cook the chicken."]
    assert r["serving_count"] == 4 and r["cooking_minutes"] == 35 and r["presentation_image_url"] == "https://x.test/a.jpg"
    assert r["nutrition"] == {"energy": 420.0, "protein": 30.0, "sodium": 800.0}, r["nutrition"]
    assert enrich(dict(r), ["Produce"]) is not None  # no key in the test env: passthrough
    print("ok: importer fixture")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        cats = json.loads((Path(__file__).parent / "categories.json").read_text())["order"]
        r = import_url(sys.argv[1], Path(sys.argv[2]), 1000001, cats)
        print(json.dumps(r, indent=1, ensure_ascii=False)[:3000])
    else:
        _selfcheck()
