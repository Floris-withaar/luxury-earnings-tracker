"""The data gate. Plain rules that every version of the dataset must pass before it can go live.

Errors stop the build: the data is malformed or a figure has no source.
Warnings do not stop it: the data is well formed but something looks unusual and a person should look.

    python -m pipeline.run validate
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from . import model
from .common import DERIVED, QUARTER_RE, REGION_KEYS, SITE, WATCHLIST, growth, is_num, load, prev_quarter, quarter_label

BASES = {"Organic", "Constant FX", "Comparable", "Reported"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GROWTH_RANGE = (-70, 150)   # percent. Outside this a quarterly growth figure is almost certainly a mistake.
SWING_PTS = 15              # a move this large against the prior quarter gets a second look
REGION_SLACK = 0.5          # rounding room when comparing the group with its regions
STALE_DAYS = 21             # days past the expected release date before a company is called stale


def _in_range(v) -> bool:
    return is_num(v) and GROWTH_RANGE[0] <= v <= GROWTH_RANGE[1]


def check_company(c: dict, errors: list, warnings: list) -> int:
    """Check one company record. Returns the number of figures looked at."""
    name = c.get("name") or c.get("id") or "?"
    figures = 0
    if not ID_RE.match(str(c.get("id", ""))):
        errors.append(f"{name}: id {c.get('id')!r} is not a lower-case slug.")
    if not c.get("name"):
        errors.append(f"{name}: no name.")
    if c.get("basis") not in BASES:
        errors.append(f"{name}: basis {c.get('basis')!r} is not one of {sorted(BASES)}.")

    sources = c.get("sources") or []
    if not sources:
        errors.append(f"{name}: no sources.")
    for i, s in enumerate(sources):
        if not s.get("t"):
            errors.append(f"{name}: source {i + 1} has no title.")
        if s.get("url") and not str(s["url"]).startswith("https://"):
            errors.append(f"{name}: source {i + 1} link is not https.")
        if s.get("kind") not in ("company", "press"):
            errors.append(f"{name}: source {i + 1} is not marked company or press.")

    def has_source(index) -> bool:
        return isinstance(index, int) and 0 <= index < len(sources)

    series = c.get("series") or {}
    if not series:
        errors.append(f"{name}: no quarterly series.")
    for q, s in series.items():
        figures += 1
        if not QUARTER_RE.match(q):
            errors.append(f"{name}: {q!r} is not a quarter like 2026Q3.")
            continue
        if not _in_range(s.get("g")):
            errors.append(f"{name} {q}: group growth {s.get('g')!r} is missing or outside {GROWTH_RANGE}.")
        if not has_source(s.get("s")):
            errors.append(f"{name} {q}: group growth has no valid source.")
        if "rev" in s and not (is_num(s["rev"]) and s["rev"] > 0):
            errors.append(f"{name} {q}: revenue {s['rev']!r} is not a positive number.")
    quarters = sorted(q for q in series if QUARTER_RE.match(q))
    for a, b in zip(quarters, quarters[1:]):
        if prev_quarter(b) != a:
            warnings.append(f"{name}: no figure between {quarter_label(a)} and {quarter_label(b)}.")
        elif is_num(series[a].get("g")) and is_num(series[b].get("g")) and abs(series[b]["g"] - series[a]["g"]) > SWING_PTS:
            warnings.append(f"{name}: growth moved {series[b]['g'] - series[a]['g']:+.1f} pts from {quarter_label(a)} to {quarter_label(b)}. Check both figures.")

    for q, cells in (c.get("regions") or {}).items():
        if q not in series:
            errors.append(f"{name}: regions for {q} but no group figure for that quarter.")
        values = []
        for key, cell in cells.items():
            figures += 1
            if key not in REGION_KEYS:
                errors.append(f"{name} {q}: {key!r} is not a region bucket.")
            if not _in_range(cell.get("v")):
                errors.append(f"{name} {q} {key}: growth {cell.get('v')!r} is missing or outside {GROWTH_RANGE}.")
            else:
                values.append(cell["v"])
            if not cell.get("label"):
                errors.append(f"{name} {q} {key}: no label from the company.")
            if not has_source(cell.get("s")):
                errors.append(f"{name} {q} {key}: no valid source.")
        g = growth(c, q)
        # A group cannot grow faster than its fastest region or slower than its slowest one.
        if g is not None and len(values) >= 3 and not (min(values) - REGION_SLACK <= g <= max(values) + REGION_SLACK):
            warnings.append(f"{name} {q}: group growth {g}% lies outside its regions ({min(values)}% to {max(values)}%). One of them is likely wrong.")

    for q, segments in (c.get("segments") or {}).items():
        if q not in series:
            errors.append(f"{name}: segments for {q} but no group figure for that quarter.")
        for seg in segments:
            figures += 1
            if not seg.get("name"):
                errors.append(f"{name} {q}: a segment has no name.")
            if "g" in seg and not _in_range(seg["g"]):
                errors.append(f"{name} {q} {seg.get('name')}: growth {seg['g']!r} is outside {GROWTH_RANGE}.")
    return figures


def validate(dataset: dict, watchlist: dict | None = None, today: date | None = None) -> dict:
    errors, warnings, figures = [], [], 0
    if not DATE_RE.match(str(dataset.get("asOf", ""))):
        errors.append("asOf is not a date like 2026-11-15.")
    companies = dataset.get("companies") or []
    if not companies:
        errors.append("The dataset has no companies.")
    ids = [c.get("id") for c in companies]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"Company id {dup!r} appears more than once.")
    for c in companies:
        figures += check_company(c, errors, warnings)
    quarters = sorted({q for c in companies for q in (c.get("series") or {}) if QUARTER_RE.match(q)})
    if quarters and dataset.get("latest") != quarters[-1]:
        errors.append(f"latest is {dataset.get('latest')!r} but the newest quarter in the data is {quarters[-1]}.")

    press = sum(1 for c in companies for cells in (c.get("regions") or {}).values() for cell in cells.values()
                if isinstance(cell.get("s"), int) and cell["s"] < len(c.get("sources") or []) and c["sources"][cell["s"]].get("kind") == "press")
    if press:
        warnings.append(f"{press} regional figures come from press reports. Replace them with company sources.")

    if watchlist:
        from .research import due_date   # imported here so the gate has no hard link to the LLM steps
        today = today or date.today()
        by_id = {c.get("id"): c for c in companies}
        for entry in watchlist.get("companies", []):
            c = by_id.get(entry["id"])
            known = sorted((c or {}).get("series") or {})
            due = due_date(entry, known[-1]) if known else None
            if due and today > due + timedelta(days=STALE_DAYS):
                warnings.append(f"{entry['name']}: a new release was expected from {due} and has not been added.")
    return {"errors": errors, "warnings": warnings, "figures": figures, "companies": len(companies)}


def check_built(dataset: dict) -> list[str]:
    """The files the site reads must match the dataset. Returns a list of problems."""
    problems = []
    fresh = json.loads(json.dumps(model.compute(dataset)))
    if load(DERIVED) != fresh:
        problems.append("data/derived.json does not match the dataset. Run: python -m pipeline.run model")
    site = load(SITE / "data.json") or {}
    if site.get("companies") != dataset["companies"] or site.get("latest") != dataset["latest"]:
        problems.append("site/data.json does not match data/companies.json. Run: python -m pipeline.run model")
    if site.get("model") != fresh:
        problems.append("The model output in site/data.json is out of date. Run: python -m pipeline.run model")
    return problems


def summary(dataset: dict) -> dict:
    """The short form shown on the site."""
    result = validate(dataset, load(WATCHLIST))
    return {"figures": result["figures"], "errors": len(result["errors"]), "warnings": result["warnings"]}
