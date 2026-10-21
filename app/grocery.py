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
from ingredients import UNITS, Q, fmt_amount, normalize_name, parse_quantity  # noqa: E402

PLURAL = {"cup", "clove", "bunch", "small bunch", "head", "medium head", "crown", "stick",
          "slice", "piece", "pint", "pkg", "can"}


def fmt_q(amount: Fraction, unit: str) -> str:
    if unit and amount > 1:
        tail = unit.rsplit(" ", 1)[-1]  # "(5 oz) pkg" -> "pkg"
        if tail in PLURAL:
            unit += "s"
    return f"{fmt_amount(amount)} {unit}".strip()


def merge(recipes, categories, overrides=None):
    """recipes: list of Mealime recipe dicts. categories: {"order": [...], "ingredients": {key: cat}}.
    overrides: {key: cat} from the user, wins over the table.
    Returns {"order": [...cats..., "Pantry"], "items": [...]} with items sorted by category order then name.
    """
    overrides = overrides or {}
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

    out = []
    for it in items.values():
        lines = []
        for g in it["groups"].values():
            # largest unit seen in this family that still gives an amount >= 1, else the smallest seen
            units = sorted(g["units"], key=lambda u: UNITS.get(u, ("", Fraction(1)))[1], reverse=True)
            unit = next((u for u in units if g["base"] / UNITS.get(u, ("", Fraction(1)))[1] >= 1), units[-1])
            lines.append(fmt_q(g["base"] / UNITS.get(unit, ("", Fraction(1)))[1], unit))
        out.append({
            "key": it["key"], "name": it["name"], "lines": lines,
            "pantry": not lines,
            "category": "Pantry" if not lines else it["category"],
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
        {"quantity": "", "ingredient_name": "salt"}]}
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
    assert by["yellow onion"]["category"] == "Frozen"
    assert len(by["chicken breast"]["sources"]) == 2
    assert [i["category"] for i in g["items"]] == sorted(
        (i["category"] for i in g["items"]), key=g["order"].index)
    # whole export merges without error
    rs = [json.loads(f.read_text()) for f in Path(export_dir, "json").glob("*.json")]
    g = merge(rs, cats)
    assert all(i["lines"] or i["pantry"] for i in g["items"])
    print(f"ok: {len(g['items'])} items from {len(rs)} recipes")


if __name__ == "__main__":
    _selfcheck(sys.argv[1] if len(sys.argv) > 1 else "mealime-export")
