"""Step 4. The model: plain arithmetic on the sourced figures. No LLM touches a number here.

For every quarter it works out, per company:
  delta            change in growth against the prior quarter, in points
  vs_median        growth minus the median of the other companies in the same industry
  median_others    that median, which leaves the company itself out
  two_year_stack   this quarter's growth compounded with the same quarter a year earlier
  base, next_base  the growth being lapped this quarter and next quarter (the comparison base)
  asia_gap         Asia ex-Japan growth minus group growth
  breadth          how many reported regions are growing
  driver           the region whose growth moved most against the prior quarter
  signal           a label built from fixed rules, defined below

Companies are compared only inside their own industry (config/categories.json), and a median
is given only when at least `min_group` companies stand behind it. Per quarter it also writes:
  groups           the same peer measures for every industry and focus group
  categories       segment growth gathered by product category across companies
"""
from __future__ import annotations

from .common import (REGIONS, all_quarters, focus_of, growth, industry_of, is_num, median, prev_quarter, region,
                     segment_category, shift_quarter, taxonomy)

# Thresholds, in percentage points. Change them here and every label follows.
MOMENTUM_PTS = 1.0      # a move of at least this much counts as accelerating or slowing
LEVEL_PTS = 2.0         # this far from the peer median counts as ahead or behind
ASIA_GAP_PTS = 3.0      # Asia this far from the group counts as a drag or a lift
BASE_SHIFT_PTS = 2.0    # next quarter's base this much higher or lower gets flagged


def _r(v, digits: int = 1):
    return round(v, digits) if is_num(v) else None


def company_metrics(company: dict, q: str, peers: list[dict], min_group: int = 3) -> dict:
    """Measures for one company. `peers` are the companies in its industry, itself included."""
    p = prev_quarter(q)
    g, g_prev = growth(company, q), growth(company, p)
    base = growth(company, shift_quarter(q, -4))        # what this quarter was compared with
    next_base = growth(company, shift_quarter(q, -3))   # what next quarter will be compared with
    others = [growth(c, q) for c in peers if c["id"] != company["id"]]
    # A median of one or two other companies says little, so the gap to it is left out.
    peer_median = median(others) if len(others) >= min_group - 1 else None
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
        "vs_median": _r(g - peer_median) if peer_median is not None else None,
        "median_others": _r(peer_median),
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


def group_stats(rows: list[dict], min_group: int) -> dict:
    """Peer measures for one set of companies. Medians only when at least `min_group` stand behind them."""
    both = [m for m in rows if m["delta"] is not None]
    gaps = [m["asia_gap"] for m in rows if m["asia_gap"] is not None]
    values = [m["growth"] for m in rows]
    # Like for like: a change in the median only uses companies that report both quarters,
    # so adding a company never shows up as a move in the median.
    asia_all = [m["asia"] for m in rows if m["asia"] is not None]
    asia_both = [m for m in rows if m["asia_delta"] is not None]
    enough = lambda xs: _r(median(xs), 2) if len(xs) >= min_group else None
    return {
        "n": len(rows),
        "median": enough(values),
        "median_like": enough([m["growth"] for m in both]),
        "median_prev": enough([m["prev"] for m in both]),
        "spread": _r(max(values) - min(values)) if len(values) >= 2 else None,
        "slowed": sum(m["delta"] < 0 for m in both),
        "compared": len(both),
        "asia_median": enough(asia_all),
        "asia_median_like": enough([m["asia"] for m in asia_both]),
        "asia_median_prev": enough([m["asia_prev"] for m in asia_both]),
        "asia_both": len(asia_both),
        "asia_lagging": sum(gap < 0 for gap in gaps),
        "asia_compared": len(gaps),
    }


def category_rows(companies: list[dict], q: str, tax: dict, min_group: int) -> dict:
    """Segment growth gathered by product category. Each line keeps its company's own basis."""
    labels = {c["id"]: c["label"] for c in tax.get("categories") or []}
    pooled = {c["id"] for c in tax.get("categories") or [] if not c.get("no_median")}
    found: dict[str, list] = {}
    for company in companies:
        for seg in (company.get("segments") or {}).get(q) or []:
            cat = segment_category(company, seg.get("name", ""), tax)
            if cat is None or not is_num(seg.get("g")):
                continue
            found.setdefault(cat, []).append({"company": company["id"], "segment": seg["name"], "g": seg["g"]})
    out = {}
    for cat in [c["id"] for c in tax.get("categories") or []] + sorted(set(found) - set(labels)):
        rows = sorted(found.get(cat, []), key=lambda r: -r["g"])
        if rows:
            out[cat] = {"label": labels.get(cat, cat), "n": len(rows), "companies": len({r["company"] for r in rows}),
                        "median": _r(median([r["g"] for r in rows]), 2) if len(rows) >= min_group and cat in pooled else None,
                        "rows": rows}
    return out


def compute(dataset: dict, tax: dict | None = None) -> dict:
    tax = taxonomy() if tax is None else tax
    min_group = int(tax.get("min_group") or 3)
    industries = [i["id"] for i in tax.get("industries") or []] or ["goods"]
    companies = dataset["companies"]
    out = {}
    for q in all_quarters(companies):
        reporting = [c for c in companies if growth(c, q) is not None]
        rows = {}
        for ind in industries:
            members = [c for c in reporting if industry_of(c, tax) == ind]
            metrics = {c["id"]: company_metrics(c, q, members, min_group) for c in members}
            ranked = sorted(metrics, key=lambda cid: -metrics[cid]["growth"])
            for cid, m in metrics.items():
                m["rank"] = ranked.index(cid) + 1
                m["rank_of"] = len(ranked)
            rows.update(metrics)

        groups = {}
        for ind in tax.get("industries") or [{"id": "goods", "label": "Peers"}]:
            ids = [c["id"] for c in reporting if industry_of(c, tax) == ind["id"]]
            groups[ind["id"]] = dict(group_stats([rows[i] for i in ids], min_group), label=ind["label"], kind="industry", members=ids)
        for f in tax.get("focus") or []:
            ids = [c["id"] for c in reporting if focus_of(c, tax) == f["id"]]
            groups[f["id"]] = dict(group_stats([rows[i] for i in ids], min_group), label=f["label"], kind="focus",
                                   industry=f.get("industry"), members=ids)
        out[q] = {
            # The headline peer group: the first industry. Every note and headline on the site reads from it.
            "peer": {k: v for k, v in groups[industries[0]].items() if k not in ("label", "kind", "members")},
            "groups": groups,
            "categories": category_rows(reporting, q, tax, min_group),
            "companies": {c["id"]: rows[c["id"]] for c in reporting},
        }
    return out
