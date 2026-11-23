"""Merge the ingredients of several recipes into one grocery list.

Rule (same as Paprika / Plan to Eat): sum only when the normalized name and
the unit family match. Different families for one food stay as separate
lines under the same item. Every merged line keeps its source recipe lines.

Self-check: python3 app/grocery.py <export_dir>
"""
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ingredients import UNITS, fmt_amount, normalize_name, parse_line, parse_quantity  # noqa: E402

PLURAL = {"cup", "clove", "bunch", "small bunch", "head", "medium head", "crown", "stick",
          "slice", "piece", "pint", "pkg", "can"}


def fmt_q(amount: Fraction, unit: str) -> str:
    if unit and amount > 1:
        tail = unit.rsplit(" ", 1)[-1]  # "(5 oz) pkg" -> "pkg"
        if tail in PLURAL:
            unit += "es" if tail.endswith("ch") else "s"
    return f"{fmt_amount(amount)} {unit}".strip()


def scale(r, servings):
    """Copy of recipe r for `servings` people: list quantities, per-step lines and serving_count rescaled.
    A recipe with no serving_count treats `servings` as a plain multiplier (1x/2x/3x) and keeps it unset.
    Results that are not already a kitchen fraction round to the nearest ⅛ (volume, mass) or ¼ (the rest); quantities the parser
    cannot read ("1 splash") stay as written. Step prose is left alone, same as Allrecipes."""
    base = r.get("serving_count")
    if not servings or servings == (base or 1):
        return r
    f = Fraction(servings) / (base or 1)

    def mul(q):
        x = q.amount * f
        if x.denominator in (1, 2, 3, 4, 6, 8):  # already a kitchen fraction (⅔ cup × 2 = 1 ⅓ cups): keep it
            return x
        step = Fraction(1, 8) if q.family in ("volume", "mass") else Fraction(1, 4)
        return max(step, Fraction(round(x / step)) * step)

    def line(s):
        q, rest = parse_line(s)
        return f"{fmt_q(mul(q), q.unit)} {rest}".strip() if q else s

    def qty(s):
        try:
            q = parse_quantity(s)
        except ValueError:
            return s
        return fmt_q(mul(q), q.unit) if q else s

    out = {**r, "serving_count": servings if base else None, "servings_base": base,
           "line_items": [{**li, "quantity": qty(li.get("quantity"))} for li in r["line_items"]],
           "instructions": [{**st, "secondary_message": "\n".join(line(l) for l in (st.get("secondary_message") or "").splitlines())} for st in r["instructions"]]}
    for st in out["instructions"]:
        st["uses"] = [l for l in st["secondary_message"].splitlines() if l.strip()]
    return out


def merge(recipes, categories, overrides=None):
    """recipes: list of Mealime recipe dicts. categories: {"order": [...], "ingredients": {key: cat}}.
    overrides: {key: cat} from the user, wins over the table.
    Returns {"order": [...cats..., "Pantry"], "items": [...]} with items sorted by category order then name.
    """
    overrides = overrides or {}
    step_groups = {}  # key -> {family: {"base", "units"}} summed from per-step lines, for pantry totals
    items = {}  # key -> {name, category, groups: {family: {"base": Fraction, "unit": str, "factor": Fraction}}, sources, pantry_sources}
    for r in recipes:
        for li in r["line_items"]:
            key = normalize_name(li["ingredient_name"])
            it = items.setdefault(key, {
                "key": key, "name": li["ingredient_name"].split(",")[0].strip(),
                "category": overrides.get(key) or categories["ingredients"].get(key, "Other"),
                "groups": {}, "sources": [], "pantry_sources": []})
            q = parse_quantity(li.get("quantity"))
            if q is None:
                it["pantry_sources"].append(r["name"])
                continue
            it["sources"].append({"recipe": r["name"], "text": f"{li['quantity'].strip()} {li['ingredient_name']}"})
            g = it["groups"].setdefault(q.family, {"base": Fraction(0), "units": set()})
            g["base"] += q.base()
            g["units"].add(q.unit)
        for st in r.get("instructions", []):
            for line in (st.get("secondary_message") or "").splitlines():
                q, name = parse_line(line)
                if q is None or not name:
                    continue
                g = step_groups.setdefault(normalize_name(name), {}).setdefault(q.family, {"base": Fraction(0), "units": set()})
                g["base"] += q.base()
                g["units"].add(q.unit)

    def fmt_groups(groups):
        lines = []
        for g in groups.values():
            # largest unit seen in this family that still gives an amount >= 1, else the smallest seen
            units = sorted(g["units"], key=lambda u: UNITS.get(u, ("", Fraction(1)))[1], reverse=True)
            unit = next((u for u in units if g["base"] / UNITS.get(u, ("", Fraction(1)))[1] >= 1), units[-1])
            lines.append(fmt_q(g["base"] / UNITS.get(unit, ("", Fraction(1)))[1], unit))
        return lines

    out = []
    for it in items.values():
        lines = fmt_groups(it["groups"])
        out.append({
            "key": it["key"], "name": it["name"], "lines": lines,
            "pantry": not lines,
            "category": "Pantry" if not lines else it["category"],
            # pantry staples have no list quantity; the per-step lines give a rough total
            "approx": fmt_groups(step_groups.get(it["key"], {})) if not lines else [],
            "sources": it["sources"] or [{"recipe": n, "text": it["name"]} for n in Counter(it["pantry_sources"])],
        })
    order = [c for c in categories["order"] if c != "Pantry"] + ["Other", "Pantry"]
    out.sort(key=lambda x: (order.index(x["category"]) if x["category"] in order else len(order), x["name"].lower()))
    return {"order": order, "items": out}


def _selfcheck(export_dir):
    import json
    cats = json.loads((Path(__file__).parent / "categories.json").read_text())
    a = {"name": "A", "line_items": [
        {"quantity": "1 lb", "ingredient_name": "chicken breasts, boneless skinless"},
        {"quantity": "2 tbsp", "ingredient_name": "soy sauce"},
        {"quantity": "2 cloves", "ingredient_name": "garlic"},
        {"quantity": "", "ingredient_name": "salt"}],
        "instructions": [{"secondary_message": "½ tsp salt\n1 lb chicken breasts"}, {"secondary_message": "¼ tsp salt"}]}
    b = {"name": "B", "line_items": [
        {"quantity": "8 oz", "ingredient_name": "chicken breasts"},
        {"quantity": "¼ cup", "ingredient_name": "soy sauce"},
        {"quantity": "4 cloves", "ingredient_name": "garlic"},
        {"quantity": "", "ingredient_name": "salt"},
        {"quantity": "1 medium", "ingredient_name": "yellow onion"}]}
    g = merge([a, b], cats, overrides={"yellow onion": "Frozen"})
    by = {i["key"]: i for i in g["items"]}
    assert by["chicken breast"]["lines"] == ["1 ½ lb"], by["chicken breast"]
    assert by["soy sauce"]["lines"] == ["6 tbsp"], by["soy sauce"]  # ¼ cup = 4 tbsp; under 1 cup so show tbsp
    assert by["garlic"]["lines"] == ["6 cloves"]
    assert by["salt"]["pantry"] and by["salt"]["category"] == "Pantry" and len(by["salt"]["sources"]) == 2
    assert by["salt"]["approx"] == ["¾ tsp"], by["salt"]
    assert by["chicken breast"]["approx"] == []  # only pantry items get step totals
    assert by["yellow onion"]["category"] == "Frozen"
    assert len(by["chicken breast"]["sources"]) == 2
    s = scale({**a, "serving_count": 4, "line_items": a["line_items"] + [{"quantity": "1 splash", "ingredient_name": "wine"}, {"quantity": "1 ½ tsp", "ingredient_name": "cumin"}]}, 6)
    assert s["serving_count"] == 6 and s["servings_base"] == 4
    assert [li["quantity"] for li in s["line_items"]] == ["1 ½ lb", "3 tbsp", "3 cloves", "", "1 splash", "2 ¼ tsp"], [li["quantity"] for li in s["line_items"]]
    assert s["instructions"][0]["uses"] == ["¾ tsp salt", "1 ½ lb chicken breasts"] and s["instructions"][1]["secondary_message"] == "⅜ tsp salt"
    assert scale(a, None) is a and scale({**a, "serving_count": 4}, 4)["line_items"] is a["line_items"]  # unset or unchanged: untouched
    assert scale({**a, "serving_count": 4}, 1)["line_items"][2]["quantity"] == "½ clove"  # 2/4 cloves rounds to the ¼ grid; never 0
    s = scale({"serving_count": 2, "line_items": [{"quantity": "⅔ cup", "ingredient_name": "rice"}, {"quantity": "1 bunch", "ingredient_name": "kale"}], "instructions": []}, 4)
    assert [li["quantity"] for li in s["line_items"]] == ["1 ⅓ cups", "2 bunches"], [li["quantity"] for li in s["line_items"]]
    s = scale(a, 3)  # no serving_count: plain multiplier
    assert s["serving_count"] is None and [li["quantity"] for li in s["line_items"]][:3] == ["3 lb", "6 tbsp", "6 cloves"] and scale(a, 1) is a
    assert [i["category"] for i in g["items"]] == sorted(
        (i["category"] for i in g["items"]), key=g["order"].index)
    # whole export merges without error
    rs = [json.loads(f.read_text()) for f in Path(export_dir, "json").glob("*.json")]
    g = merge(rs, cats)
    assert all(i["lines"] or i["pantry"] for i in g["items"])
    print(f"ok: {len(g['items'])} items from {len(rs)} recipes")


if __name__ == "__main__":
    _selfcheck(sys.argv[1] if len(sys.argv) > 1 else "mealime-export")
