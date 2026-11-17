"""Shared helpers: file paths, JSON in and out, quarter arithmetic, medians."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
COMPANIES = DATA / "companies.json"      # the sourced dataset, edited only through review
DERIVED = DATA / "derived.json"          # output of the model stage
COMMENTARY = DATA / "commentary.json"    # output of the interpret stage
REVIEW = DATA / "review"                 # drafts waiting for a human
WATCHLIST = ROOT / "config" / "watchlist.json"

# The five region buckets every company is mapped into.
REGIONS = [
    ("asia", "Asia ex-Japan"),
    ("japan", "Japan"),
    ("europe", "Europe"),
    ("americas", "Americas"),
    ("me", "Middle East & other"),
]
REGION_KEYS = [k for k, _ in REGIONS]
# Names the extraction prompt uses for the buckets.
STANDARD_TO_KEY = {
    "asia_ex_japan": "asia",
    "japan": "japan",
    "europe": "europe",
    "americas": "americas",
    "middle_east_other": "me",
}
QUARTER_RE = re.compile(r"^\d{4}Q[1-4]$")
# The growth bases a company can report on.
BASES = ["Organic", "Constant FX", "Comparable", "Reported"]
# Percent. A quarterly growth figure outside this range is almost certainly a mistake.
GROWTH_RANGE = (-70, 150)


def plausible(v) -> bool:
    return is_num(v) and GROWTH_RANGE[0] <= v <= GROWTH_RANGE[1]


def load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def shift_quarter(q: str, n: int) -> str:
    """shift_quarter('2026Q1', -1) -> '2025Q4'."""
    year, quarter = int(q[:4]), int(q[5])
    index = year * 4 + (quarter - 1) + n
    return f"{index // 4}Q{index % 4 + 1}"


def prev_quarter(q: str) -> str:
    return shift_quarter(q, -1)


def quarter_label(q: str) -> str:
    return f"Q{q[5]} {q[:4]}"


def median(values) -> float | None:
    v = sorted(x for x in values if is_num(x))
    if not v:
        return None
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


def growth(company: dict, q: str) -> float | None:
    s = (company.get("series") or {}).get(q)
    return s["g"] if s and is_num(s.get("g")) else None


def region(company: dict, q: str, key: str) -> float | None:
    cell = ((company.get("regions") or {}).get(q) or {}).get(key)
    return cell["v"] if cell and is_num(cell.get("v")) else None


def all_quarters(companies: list[dict]) -> list[str]:
    return sorted({q for c in companies for q in (c.get("series") or {})})


def fmt_pct(v) -> str:
    if not is_num(v):
        return "n/d"
    r = round(v, 1)
    if r == 0:
        return "0%"
    body = f"{abs(r):.1f}".rstrip("0").rstrip(".")
    return ("+" if r > 0 else "−") + body + "%"


def fmt_pts(v) -> str:
    if not is_num(v):
        return ""
    r = round(v, 1)
    body = f"{abs(r):.1f}".rstrip("0").rstrip(".")
    unit = " pt" if body == "1" else " pts"
    return ("+" if r > 0 else "−" if r < 0 else "") + body + unit


def slugify(name: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFD", name.lower())
    plain = "".join(ch for ch in plain if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:40] or "company"


def skipped_quarters(entry: dict | None) -> set[int]:
    """Calendar quarters (1 to 4) for which the company publishes no quarter-only figure.

    Never all four, or the search for the next release would have nowhere to land.
    """
    found = {int(n) for n in ((entry or {}).get("skip_quarters") or []) if str(n) in ("1", "2", "3", "4")}
    return found if len(found) < 4 else set()
