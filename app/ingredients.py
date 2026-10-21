"""Parse Mealime quantity strings and ingredient lines. Stdlib only.

Mealime uses a small closed vocabulary (43 quantity patterns across 982
line items, checked 2026-10-20). This parser targets that vocabulary, not
free-text recipes.

    parse_quantity("1 ½ lb")       -> Q(amount=3/2, unit="lb", family="mass")
    parse_quantity("2 (5 oz) pkgs") -> Q(amount=2, unit="(5 oz) pkg", family="pkg:(5 oz) pkg")
    parse_quantity("")              -> None  (pantry item, no quantity)
    parse_line("½ tsp salt")        -> (Q(...), "salt")

Self-check: python3 app/ingredients.py <export_dir>
"""
import re
import sys
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

VULGAR = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8"}
_NUM = r"(?P<num>\d+(?:\.\d+)?(?:\s*[½¼¾⅓⅔⅛])?|[½¼¾⅓⅔⅛]|\d+/\d+)"

# canonical unit -> (family, factor to family base unit). Base: tsp for volume, oz for mass.
UNITS = {
    "tsp": ("volume", Fraction(1)),
    "tbsp": ("volume", Fraction(3)),
    "fl oz": ("volume", Fraction(6)),
    "cup": ("volume", Fraction(48)),
    "pint": ("volume", Fraction(96)),
    "ml": ("volume", Fraction(1, 5)),  # kitchen convention, 5 ml = 1 tsp
    "oz": ("mass", Fraction(1)),
    "lb": ("mass", Fraction(16)),
}
# count-like units: each is its own family, no conversion
COUNT_UNITS = ["clove", "medium head", "medium", "small bunch", "bunch", "head", "crown",
               "stick", "slice", "(1 inch) piece", "small pkg"]
_ALIASES = {"cups": "cup", "cloves": "clove", "bunches": "bunch", "small bunches": "small bunch",
            "heads": "head", "medium heads": "medium head", "crowns": "crown", "sticks": "stick",
            "slices": "slice", "(1 inch) pieces": "(1 inch) piece", "pkgs": "pkg", "cans": "can"}
_PKG = r"\((?P<size>\d+(?:\.\d+)?\s*oz)\)\s*(?P<kind>pkgs?|cans?|block|bag|jar|whole chicken)"
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(
    list(UNITS) + COUNT_UNITS + list(_ALIASES), key=len, reverse=True))
_QTY_RE = re.compile(rf"^{_NUM}\s*(?:(?P<pkg>{_PKG})|(?P<unit>{_UNIT_ALT}))?(?=\s|$)")

_PLURAL_EXCEPT = {"asparagus", "couscous", "hummus", "brussels"}


@dataclass(frozen=True)
class Q:
    amount: Fraction
    unit: str          # canonical display unit, "" for a bare count
    family: str        # merge key: volume, mass, count, or the unit itself

    def base(self) -> Fraction:
        """Amount in the family's base unit (tsp, oz, or itself)."""
        return self.amount * UNITS.get(self.unit, ("", Fraction(1)))[1]


def _number(s: str) -> Fraction:
    for k, v in VULGAR.items():
        s = s.replace(k, " " + v)
    return sum(Fraction(p) for p in s.split())


def _match(s: str):
    s = s.strip()
    if not s:
        return None, ""
    m = _QTY_RE.match(s)
    if not m:
        raise ValueError(f"unparsed quantity: {s!r}")
    amount = _number(m.group("num"))
    if m.group("pkg"):
        kind = _ALIASES.get(m.group("kind"), m.group("kind"))
        unit = f"({m.group('size')}) {kind}"
        q = Q(amount, unit, "pkg:" + unit)
    elif m.group("unit"):
        unit = _ALIASES.get(m.group("unit"), m.group("unit"))
        q = Q(amount, unit, UNITS[unit][0] if unit in UNITS else unit)
    else:
        q = Q(amount, "", "count")
    return q, s[m.end():].strip()


def parse_quantity(s: Optional[str]) -> Optional[Q]:
    """Mealime line_items[].quantity. None for empty (pantry) quantities."""
    q, rest = _match(s or "")
    if rest:
        raise ValueError(f"trailing text in quantity: {s!r}")
    return q


def parse_line(s: str):
    """One line of instructions[].secondary_message: '½ tsp salt' -> (Q, 'salt').

    Display-only, so phrasings like 'juice of 1 lemon' come back as (None, line).
    """
    try:
        return _match(s)
    except ValueError:
        return None, s.strip()


def normalize_name(name: str) -> str:
    """Merge key for an ingredient: lowercase, drop ', qualifier' and '(aside)', singularise."""
    n = name.lower().split(",")[0]
    n = re.sub(r"\s*\([^)]*\)", "", n).strip()
    words = n.split()
    if words:
        w = words[-1]
        if w.endswith("oes"):
            w = w[:-2]
        elif w.endswith("s") and not w.endswith("ss") and w not in _PLURAL_EXCEPT:
            w = w[:-1]
        words[-1] = w
    return " ".join(words)


def fmt_amount(x: Fraction) -> str:
    whole, frac = divmod(x, 1)
    inv = {v: k for k, v in VULGAR.items()}
    f = inv.get(str(frac), str(frac) if frac else "")
    return f"{int(whole) if whole else ''}{' ' if whole and f else ''}{f}".strip() or "0"


def _selfcheck(export_dir):
    import json
    from pathlib import Path
    n = lines = verbatim = 0
    for f in Path(export_dir, "json").glob("*.json"):
        r = json.loads(f.read_text())
        for li in r["line_items"]:
            parse_quantity(li["quantity"]); n += 1
            assert normalize_name(li["ingredient_name"]), li
        for st in r["instructions"]:
            for l in (st.get("secondary_message") or "").splitlines():
                if l.strip():
                    q, name = parse_line(l); lines += 1
                    verbatim += q is None
                    assert name, l
    assert parse_quantity("1 ½ lb") == Q(Fraction(3, 2), "lb", "mass")
    assert parse_quantity("2 (5 oz) pkgs") == Q(Fraction(2), "(5 oz) pkg", "pkg:(5 oz) pkg")
    assert parse_quantity("16 fl oz").base() == Fraction(96)
    assert parse_line("½ tsp salt") == (Q(Fraction(1, 2), "tsp", "volume"), "salt")
    assert parse_line("1 medium yellow onion") == (Q(Fraction(1), "medium", "medium"), "yellow onion")
    assert normalize_name("chicken breasts, boneless skinless") == "chicken breast"
    assert normalize_name("green onions (scallions)") == "green onion"
    assert normalize_name("tomatoes") == "tomato" and normalize_name("asparagus") == "asparagus"
    assert fmt_amount(Fraction(3, 2)) == "1 ½" and fmt_amount(Fraction(2)) == "2"
    assert verbatim <= 10, verbatim  # 8 known phrasings like 'juice of 1 lemon'
    print(f"ok: {n} quantities, {lines} step lines parsed ({verbatim} verbatim)")


if __name__ == "__main__":
    _selfcheck(sys.argv[1] if len(sys.argv) > 1 else "mealime-export")
