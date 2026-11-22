"""Import a recipe from a web page, PDF, image or plain text into the Mealime JSON shape the app reads.

Path: fetch page -> schema.org Recipe JSON-LD -> Mealime-shaped dict -> optional
Claude pass (per-step ingredient lines, cookware, aisle categories) -> json + image
+ markdown under <dest>/. A PDF, image or text file goes through one Claude call that
returns the same schema.org shape (plus per-step lines and tools), then the same path.
Stdlib only; Claude via urllib against the Messages API.

Self-check: python3 app/importer.py            (fixture, no network)
Manual:     python3 app/importer.py <url> <dest_dir>
"""
from __future__ import annotations

import base64
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
_FRACS = [(0.125, "⅛"), (0.25, "¼"), (0.333, "⅓"), (0.5, "½"), (0.667, "⅔"), (0.75, "¾")]


def dec_to_frac(d: str) -> str:
    """'1.5' -> '1 ½', '0.33333334326744' -> '⅓' (Allrecipes float32 thirds). Unrecognised -> unchanged."""
    v = float(d)
    whole, frac = int(v), v - int(v)
    sym = next((s for f, s in _FRACS if abs(frac - f) < 0.02), None)
    if sym is None:
        return d
    return f"{whole} {sym}" if whole else sym

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
    s = re.sub(r"^\d*\.\d+", lambda m: dec_to_frac(m.group(0)), s).strip()  # "0.25" -> "¼", "1.5" -> "1 ½", "0.33333334326744" -> "⅓"
    s = re.sub(r"^(\d+) ?([½¼¾⅓⅔⅛])", r"\1 \2", s)  # "1½" -> "1 ½"
    s = re.sub(r"\((\d+(?:\.\d+)?)[ -]?(?:ounces?|oz\.?)\)", r"(\1 oz)", s, flags=re.I)  # "(28 ounce) can" -> "(28 oz) can", the parser's package form
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
    return s[: len(s) - len(rest)].strip(), re.sub(r"^\([^)]*\)\s*", "", rest)  # "3 cup (360g) flour" -> name "flour"


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


def _claude(content, max_tokens: int = 4000) -> dict:
    """One Messages call; the JSON object in its reply. content: prompt string or content blocks."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    body = json.dumps({"model": MODEL, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        text = "".join(b.get("text", "") for b in json.loads(resp.read())["content"])
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def enrich(r: dict, aisles: list) -> dict:
    """One Claude call: per-step ingredient lines, cookware, aisle per ingredient. No key -> unchanged.
    Steps and cookware already filled (document imports) are kept."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
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

Rules: "steps" lists the ingredients used in each step with the amount used in that step (split an ingredient across steps if the recipe does; omit steps that use none). Every ingredient must appear in at least one step; "combine all ingredients" means list all of them there. Write amounts with unicode fractions and short units (tsp, tbsp, cup, oz, lb). "cookwares" is the kitchen equipment needed (pans, bowls, knife, etc.). "categories" maps every ingredient to one of: {", ".join(aisles)}."""
    data = _claude(prompt)
    for s in r["instructions"]:
        if not s.get("secondary_message"):
            s["secondary_message"] = "\n".join(_norm_line(x) for x in data.get("steps", {}).get(str(s["id"])) or [])
    r["cookwares"] = r.get("cookwares") or _cookwares(data.get("cookwares"))
    r["_categories"] = {str(k): v for k, v in (data.get("categories") or {}).items() if v in aisles}
    return r


def _norm_line(line) -> str:
    """Step ingredient line through the same quantity normalisation as the ingredient list ("1/2 Tbsp" -> "½ tbsp")."""
    q, n = split_ingredient(str(line))
    return f"{q} {n}".strip()


def _cookwares(names) -> list:
    return [{"id": i + 1, "name": str(c), "slug": re.sub(r"\W+", "-", str(c).lower())} for i, c in enumerate(names or [])]


DOC_PROMPT = """This is a recipe (PDF, image or plain text). Return it as JSON only, no prose, shape:
{"name": "...", "recipeYield": "4 servings", "totalTime": "PT35M", "recipeIngredient": ["2 tbsp soy sauce", ...], "recipeInstructions": ["step text", ...], "stepIngredients": {"1": ["1 cup jasmine rice", ...]}, "tool": ["chef's knife", ...], "nutrition": {"calories": "407 kcal", "fatContent": "15 g", "carbohydrateContent": "37 g", "proteinContent": "30 g", "fiberContent": "4 g", "sodiumContent": "221 mg", "sugarContent": "5 g"}}

Rules: recipeIngredient is the full ingredient list, one entry per ingredient, quantity first, then unit, then the name as written ("1 ½ lb chicken breasts, boneless skinless"; no quantity for to-taste or pantry items). recipeInstructions is every step in order without its number, text verbatim, no headings. stepIngredients maps the 1-based step number to the ingredient lines used in that step with the amount used there: if the document lists ingredients under each step (indented or italic lines below the step text), copy those exactly; otherwise work them out from the step text, splitting an ingredient across steps when the recipe does. Every ingredient appears in at least one step. tool is the document's equipment list if it has one, else the equipment the steps need. "Makes 6 meals" means recipeYield "6 servings". Omit nutrition keys the document does not state; values are per serving. Ignore prices, ratings, ads, author notes and site chrome. If there is more than one recipe, return only the first."""


def sniff(data: bytes) -> str:
    """Media type from magic bytes; anything that decodes as UTF-8 is text."""
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp":
        raise ValueError("HEIC/HEIF not supported, share it as JPEG")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("not a PDF, PNG, JPEG, WebP or text file") from None
    return "text/plain"


def from_document(data: bytes | str, media_type: str) -> dict:
    """PDF, image or plain text -> schema.org-shaped dict (plus stepIngredients and tool) via one Claude call.
    media_type "auto" sniffs it from the bytes."""
    if media_type == "auto":
        media_type = sniff(data)
    if media_type == "text/plain":
        text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
        return _claude(DOC_PROMPT + "\n\nRecipe:\n" + text, 6000)
    block = "document" if media_type == "application/pdf" else "image"
    return _claude([{"type": block, "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()}},
                    {"type": "text", "text": DOC_PROMPT}], 6000)


def document_to_mealime(ld: dict, rid: int, source: str) -> dict:
    r = to_mealime(ld, rid, source)
    for s in r["instructions"]:
        s["secondary_message"] = "\n".join(_norm_line(x) for x in (ld.get("stepIngredients") or {}).get(str(s["id"])) or [])
    r["cookwares"] = _cookwares(ld.get("tool"))
    return r


def pdf_photo(data: bytes) -> bytes | None:
    """Largest JPEG stream in a PDF: browser and Canva prints keep the recipe photo as DCTDecode.
    Small ones are icons. ponytail: Flate (raw pixel) images are skipped, no PNG writer here."""
    best = b""
    for m in re.finditer(rb"stream\r?\n(?=\xff\xd8\xff)", data):
        start, end = m.end(), data.find(b"endstream", m.end())
        if end > start and end - start > len(best):
            best = data[start:end]
    return best.rstrip(b"\r\n") if len(best) > 20_000 else None


def import_document(data: bytes | str, media_type: str, source: str, dest: Path, rid: int) -> dict:
    """One Claude call on the file, then the same save path as a URL import. The photo comes out of
    the PDF when it has one. Needs ANTHROPIC_API_KEY."""
    r = document_to_mealime(from_document(data, media_type), rid, source)
    stem = f"{r['slug']}-{rid}"
    (dest / "json").mkdir(parents=True, exist_ok=True)
    (dest / "images").mkdir(exist_ok=True)
    image = None
    if isinstance(data, bytes) and data.startswith(b"%PDF"):
        photo = (pdf_photo(data), ".jpg") if pdf_photo(data) else None
    else:
        text = data if isinstance(data, str) else data.decode("utf-8", "replace") if media_type in ("auto", "text/plain") else ""
        photo = _photo_from_link(text) if text else None
    if photo:
        (dest / "images" / (stem + photo[1])).write_bytes(photo[0])
        image = f"images/{stem}{photo[1]}"
    r["_image"] = image
    _save(r, dest, source, image)
    return r


def _save(r: dict, dest: Path, url: str, image: str | None):
    stem = f"{r['slug']}-{r['id']}"
    tmp = dest / "json" / f"{stem}.json.tmp"
    tmp.write_text(json.dumps(r, indent=1, ensure_ascii=False))
    os.replace(tmp, dest / "json" / f"{stem}.json")
    try:
        from mealime_export import to_markdown
        (dest / f"{stem}.md").write_text(to_markdown(r, url, url, image).replace("tags: [recipe, mealime]", "tags: [recipe, imported]"))
    except ImportError:  # ponytail: md is a nicety; the app reads the json
        pass


def _download_image(url: str) -> tuple[bytes, str]:
    img = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20)
    ext = Path(urlparse(url).path).suffix.lower()
    return img.read(MAX_BYTES), ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"


def _photo_from_link(text: str) -> tuple[bytes, str] | None:
    """A pasted note usually carries its source link: take that page's schema.org image if the site answers."""
    m = re.search(r"https?://[^\s<>\"']+", text)
    if not m:
        return None
    try:
        url = image_of(find_recipe(fetch(m.group().rstrip(".,)"))))
        return _download_image(url) if url else None
    except Exception:  # ponytail: 403s, dead links and non-recipe pages just mean no photo
        return None


def import_url(url: str, dest: Path, rid: int, html: str | None = None) -> dict:
    """Fetch (or take the page html from a browser-side fetch, since many recipe sites 403
    non-browser TLS fingerprints), convert, save json/image/markdown under dest. Fast path,
    no AI; call enrich_saved() afterwards (the server does it in a background thread so a
    share-sheet Shortcut gets its reply within its ~30 s budget)."""
    r = to_mealime(find_recipe(html or fetch(url)), rid, url)
    stem = f"{r['slug']}-{rid}"
    (dest / "json").mkdir(parents=True, exist_ok=True)
    (dest / "images").mkdir(exist_ok=True)
    image = None
    if r.get("presentation_image_url"):
        try:
            data, ext = _download_image(r["presentation_image_url"])
            (dest / "images" / (stem + ext)).write_bytes(data)
            image = f"images/{stem}{ext}"
        except Exception:  # ponytail: no photo is fine
            pass
    r["_image"] = image
    _save(r, dest, url, image)
    return r


def enrich_saved(r: dict, dest: Path, aisles: list) -> dict:
    """Claude pass on an already saved recipe; rewrites its json and md."""
    r = enrich(r, aisles)
    _save(r, dest, r.get("source_url", ""), r.get("_image"))
    return r


def _selfcheck():
    html = """<html><script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"WebPage"},
    {"@type":["Recipe"],"name":"Test Stir Fry","image":{"@type":"ImageObject","url":"https://x.test/a.jpg"},
    "recipeYield":["4","4 servings"],"totalTime":"PT35M","nutrition":{"@type":"NutritionInformation","calories":"420 kcal","sodiumContent":"0.8 g","proteinContent":"30 g"},
    "recipeIngredient":["2 tablespoons soy sauce","1 (28 ounce) can crushed tomatoes","2 (15-oz) cans black beans","3 cups (360g) flour","0.25 cup olive oil","1.5 tsp cumin","0.33333334326744 cup butter","0.66666668653488 cup milk","1/2 to 2/3 cup hot water","1 1/2 pounds chicken thighs, boneless","3 cloves garlic, minced","1&frac12; cups of rice","salt to taste","2-3 green onions","100 g snap peas"],
    "recipeInstructions":[{"@type":"HowToSection","name":"Prep","itemListElement":[{"@type":"HowToStep","text":"Mince the garlic."}]},{"@type":"HowToStep","text":"Cook the <b>chicken</b>."}]}]}</script></html>"""
    ld = find_recipe(html)
    r = to_mealime(ld, 1000001, "https://x.test/r")
    got = [(li["quantity"], li["ingredient_name"]) for li in r["line_items"]]
    assert got == [("2 tbsp", "soy sauce"), ("1 (28 oz) can", "crushed tomatoes"), ("2 (15 oz) cans", "black beans"), ("3 cup", "flour"), ("¼ cup", "olive oil"), ("1 ½ tsp", "cumin"), ("⅓ cup", "butter"), ("⅔ cup", "milk"), ("½ cup", "hot water"), ("1 ½ lb", "chicken thighs, boneless"), ("3 cloves", "garlic, minced"),
                   ("1 ½ cup", "rice"), ("", "salt"), ("2", "green onions"), ("100 g", "snap peas")], got
    assert [s["primary_message"] for s in r["instructions"]] == ["Mince the garlic.", "Cook the chicken."]
    assert r["serving_count"] == 4 and r["cooking_minutes"] == 35 and r["presentation_image_url"] == "https://x.test/a.jpg"
    assert r["nutrition"] == {"energy": 420.0, "protein": 30.0, "sodium": 800.0}, r["nutrition"]
    assert enrich(dict(r), ["Produce"]) is not None  # no key in the test env: passthrough
    d = document_to_mealime({"name": "Doc Soup", "recipeYield": "6 servings", "recipeIngredient": ["2 lbs hash browns", "1 tsp salt"],
                             "recipeInstructions": ["Brown the beef.", "Add salt."], "stepIngredients": {"2": ["1/2 Tbsp salt", "2 lbs beef"]}, "tool": ["skillet"]}, 1000002, "Doc Soup.pdf")
    assert [s["secondary_message"] for s in d["instructions"]] == ["", "½ tbsp salt\n2 lb beef"], d["instructions"] and d["cookwares"][0]["name"] == "skillet" and d["serving_count"] == 6
    fake = b"%PDF\nstream\n\xff\xd8\xff" + b"x" * 30000 + b"\nendstream\nstream\n\xff\xd8\xffsmall\nendstream\n"
    assert pdf_photo(fake).startswith(b"\xff\xd8\xff") and len(pdf_photo(fake)) == 30003 and pdf_photo(b"%PDF no images") is None
    assert sniff(b"%PDF-1.4") == "application/pdf" and sniff("2 cups water".encode()) == "text/plain" and sniff(b"\xff\xd8\xffdata") == "image/jpeg"
    for bad in (b"\x00\x00\x00\x18ftypheic", b"\x00\x01\xff\xfe"):
        try:
            sniff(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    assert _photo_from_link("no links here") is None and _photo_from_link("Link: https://127.0.0.1:9/x") is None
    print("ok: importer fixture")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        cats = json.loads((Path(__file__).parent / "categories.json").read_text())["order"]
        r = enrich_saved(import_url(sys.argv[1], Path(sys.argv[2]), 1000001), Path(sys.argv[2]), cats)
        print(json.dumps(r, indent=1, ensure_ascii=False)[:3000])
    else:
        _selfcheck()
