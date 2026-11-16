"""Step 4. The model: plain arithmetic on the sourced figures. No LLM touches a number here.

For every quarter it works out, per company:
  delta            change in growth against the prior quarter, in points
  vs_median        growth minus the median of the other companies
  two_year_stack   this quarter's growth compounded with the same quarter a year earlier
  base, next_base  the growth being lapped this quarter and next quarter (the comparison base)
  asia_gap         Asia ex-Japan growth minus group growth
  breadth          how many reported regions are growing
  driver           the region whose growth moved most against the prior quarter
  signal           a label built from fixed rules, defined below
"""
from __future__ import annotations

from .common import REGIONS, all_quarters, growth, is_num, median, prev_quarter, region, shift_quarter

# Thresholds, in percentage points. Change them here and every label follows.
MOMENTUM_PTS = 1.0      # a move of at least this much counts as accelerating or slowing
LEVEL_PTS = 2.0         # this far from the peer median counts as ahead or behind
ASIA_GAP_PTS = 3.0      # Asia this far from the group counts as a drag or a lift
BASE_SHIFT_PTS = 2.0    # next quarter's base this much higher or lower gets flagged


def _r(v, digits: int = 1):
    return round(v, digits) if is_num(v) else None


def company_metrics(company: dict, q: str, peers: list[dict]) -> dict:
    p = prev_quarter(q)
    g, g_prev = growth(company, q), growth(company, p)
    base = growth(company, shift_quarter(q, -4))        # what this quarter was compared with
    next_base = growth(company, shift_quarter(q, -3))   # what next quarter will be compared with
    others = [growth(c, q) for c in peers if c["id"] != company["id"]]
    asia, asia_prev = region(company, q, "asia"), region(company, p, "asia")

    # Each region goes by the company's own name for it. Moncler's Asia includes Japan, for one, so the bucket name would mislead.
    labels = (company.get("regions") or {}).get(q) or {}
    cells = [(key, (labels.get(key) or {}).get("label") or name, region(company, q, key), region(company, p, key)) for key, name in REGIONS]
    reported = [c for c in cells if c[2] is not None]
    growing = [c for c in reported if c[2] > 0]
    moved = [(key, name, now - before) for key, name, now, before in cells if now is not None and before is not None]
    driver = max(moved, key=lambda m: abs(m[2])) if moved else None

    m = {
        "growth": g,
        "prev": g_prev,
        "delta": _r(g - g_prev) if g_prev is not None else None,
        "vs_median": _r(g - median(others)) if median(others) is not None else None,
        "two_year_stack": _r(((1 + g / 100) * (1 + base / 100) - 1) * 100) if base is not None else None,
        "base": base,
        "next_base": next_base,
        "asia": asia,
        "asia_prev": asia_prev,
        "asia_gap": _r(asia - g) if asia is not None else None,
        "asia_delta": _r(asia - asia_prev) if asia is not None and asia_prev is not None else None,
        "breadth": {"growing": len(growing), "reported": len(reported)},
        "region_spread": _r(max(c[2] for c in reported) - min(c[2] for c in reported)) if len(reported) >= 2 else None,
        "driver": {"key": driver[0], "name": driver[1], "change": _r(driver[2])} if driver else None,
    }
    m["signal"] = signal(m)
    return m


def signal(m: dict) -> dict:
    """A label built from fixed rules, so the same numbers always give the same words."""
    d, rel = m["delta"], m["vs_median"]
    momentum = "No prior quarter" if d is None else "Accelerating" if d >= MOMENTUM_PTS else "Slowing" if d <= -MOMENTUM_PTS else "Steady"
    level = "" if rel is None else "ahead of peers" if rel >= LEVEL_PTS else "behind peers" if rel <= -LEVEL_PTS else "in line with peers"
    flags = []
    if m["asia_gap"] is not None:
        if m["asia_gap"] <= -ASIA_GAP_PTS:
            flags.append("Asia drag")
        elif m["asia_gap"] >= ASIA_GAP_PTS:
            flags.append("Asia lift")
    b = m["breadth"]
    if b["reported"] >= 3 and b["growing"] / b["reported"] < 0.5:
        flags.append("Narrow growth")
    if m["base"] is not None and m["next_base"] is not None:
        shift = m["next_base"] - m["base"]
        if shift >= BASE_SHIFT_PTS:
            flags.append("Tougher base next quarter")
        elif shift <= -BASE_SHIFT_PTS:
            flags.append("Easier base next quarter")
    return {"momentum": momentum, "level": level, "flags": flags, "label": momentum + (", " + level if level else "")}


def compute(dataset: dict) -> dict:
    companies = dataset["companies"]
    out = {}
    for q in all_quarters(companies):
        peers = [c for c in companies if growth(c, q) is not None]
        rows = {c["id"]: company_metrics(c, q, peers) for c in peers}

        ranked = sorted(rows, key=lambda cid: -rows[cid]["growth"])
        for cid, m in rows.items():
            m["rank"] = ranked.index(cid) + 1

        both = [m for m in rows.values() if m["delta"] is not None]
        gaps = [m["asia_gap"] for m in rows.values() if m["asia_gap"] is not None]
        values = [m["growth"] for m in rows.values()]
        # Like for like: a change in the median only uses companies that report both quarters,
        # so adding a company never shows up as a move in the median.
        asia_both = [m for m in rows.values() if m["asia_delta"] is not None]
        out[q] = {
            "peer": {
                "n": len(peers),
                "median": _r(median(values), 2),
                "median_like": _r(median([m["growth"] for m in both]), 2),
                "median_prev": _r(median([m["prev"] for m in both]), 2),
                "spread": _r(max(values) - min(values)) if values else None,
                "slowed": sum(m["delta"] < 0 for m in both),
                "compared": len(both),
                "asia_median": _r(median([m["asia"] for m in rows.values()]), 2),
                "asia_median_like": _r(median([m["asia"] for m in asia_both]), 2),
                "asia_median_prev": _r(median([m["asia_prev"] for m in asia_both]), 2),
                "asia_both": len(asia_both),
                "asia_lagging": sum(gap < 0 for gap in gaps),
                "asia_compared": len(gaps),
            },
            "companies": rows,
        }
    return out
