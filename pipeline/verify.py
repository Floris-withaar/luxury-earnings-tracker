"""Step 3. Verify: deterministic checks on what the LLM extracted. No model is involved here.

Each figure gets one of three results:
  ok    the quoted words are in the release and the number is in the quote
  part  only one of the two holds
  miss  neither holds
A draft is merged automatically only when every figure is ok and no sanity flag is raised.
"""
from __future__ import annotations

import re

from .common import QUARTER_RE, REGION_KEYS, growth, is_num, plausible


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[−‒–—]", "-", s)
    return re.sub(r"[ \s|]+", " ", s).strip()


def squash(s: str) -> str:
    return re.sub(r"\s+", "", norm(s))


def _number_forms(value: float) -> list[str]:
    body = f"{abs(round(value, 1)):.1f}".rstrip("0").rstrip(".")
    forms = [body, body.replace(".", ",")]
    if "." not in body:
        forms += [body + ".0", body + ",0"]
    return forms


def check_figure(value, quote: str, doc_norm: str, doc_squash: str) -> str:
    if not quote:
        return "miss"
    in_doc = norm(quote) in doc_norm or (len(squash(quote)) > 5 and squash(quote) in doc_squash)
    in_quote = False
    if is_num(value):
        q = re.sub(r"(\d)[ ,](\d{3})(?!\d)", r"\1\2", norm(quote))
        for form in _number_forms(value):
            if re.search(r"(^|[^0-9.,])" + re.escape(form) + r"(?![0-9])", q):
                in_quote = True
                break
        if value == 0 and re.search(r"flat|stable|unchanged", q):
            in_quote = True
    if in_doc and in_quote:
        return "ok"
    return "part" if (in_doc or in_quote) else "miss"


def verify_draft(draft: dict, text: str, existing: dict | None = None) -> dict:
    """Add a check to every figure and a list of sanity flags to the draft."""
    doc_norm, doc_squash = norm(text), squash(text)
    flags = []
    for fig in draft["figures"]:
        fig["check"] = check_figure(fig.get("v"), fig.get("quote", ""), doc_norm, doc_squash)
        if is_num(fig.get("v")) and not plausible(fig["v"]):
            flags.append(f"{fig['label']}: growth of {fig['v']}% is outside the plausible range.")
    quarter = draft.get("calendar_quarter")
    if not (isinstance(quarter, str) and QUARTER_RE.match(quarter)):
        flags.append("No valid calendar quarter.")
    if not is_num(draft["figures"][0].get("v")):
        flags.append("No group growth figure for the quarter.")
    buckets = [f.get("bucket") for f in draft["figures"] if f["kind"] == "region"]
    if any(b not in REGION_KEYS for b in buckets) or len(buckets) != len(set(buckets)):
        flags.append("Region buckets are invalid or repeated.")
    if existing and quarter:
        old = growth(existing, quarter)
        new = draft["figures"][0].get("v")
        if old is not None and is_num(new) and abs(old - new) > 0.05:
            flags.append(f"Group growth {new}% differs from the stored {old}% for {quarter}.")
    counts = {"ok": 0, "part": 0, "miss": 0}
    for fig in draft["figures"]:
        counts[fig["check"]] += 1
    draft["checks"] = {"ok": counts["ok"], "total": len(draft["figures"]), "part": counts["part"], "miss": counts["miss"]}
    draft["flags"] = flags
    draft["auto_merge"] = counts["ok"] == len(draft["figures"]) and not flags
    return draft


def merge_draft(dataset: dict, draft: dict) -> dict:
    """Write a reviewed draft into the dataset. Returns the company record."""
    quarter = draft["calendar_quarter"]
    info = draft["company"]
    company = next((c for c in dataset["companies"] if c["id"] == info["id"] or c["name"].lower() == info["name"].lower()), None)
    if company is None:
        company = {"id": info["id"], "name": info["name"], "ticker": info.get("ticker", ""), "hq": info.get("hq", ""),
                   "basis": info.get("basis", "Reported"), "cur": info.get("cur") or "EUR", "origin": "pipeline",
                   "series": {}, "regions": {}, "segments": {}, "sources": []}
        dataset["companies"].append(company)
    src = draft.get("source") or {}
    source = {"t": src.get("title") or f"Results release for {draft.get('period_label') or quarter}",
              "pub": src.get("publisher") or company["name"], "date": src.get("published") or "", "url": src.get("url") or "",
              "kind": src.get("kind") if src.get("kind") in ("company", "press") else "company"}
    urls = [s.get("url") for s in company["sources"]]
    if source["url"] and source["url"] in urls:
        index = urls.index(source["url"])
    else:
        company["sources"].append(source)
        index = len(company["sources"]) - 1

    group = draft["figures"][0]
    entry = {"g": group["v"], "s": index}
    if group.get("quote"):
        entry["q"] = group["quote"]
    if draft.get("period_label"):
        entry["label"] = draft["period_label"]
    if is_num(group.get("rev")):
        entry["rev"] = group["rev"]
    company["series"][quarter] = entry

    regions, segments = {}, []
    for fig in draft["figures"][1:]:
        if fig["kind"] == "region" and is_num(fig.get("v")):
            cell = {"v": fig["v"], "label": fig["label"], "s": index}
            if fig.get("quote"):
                cell["q"] = fig["quote"]
            if fig.get("note"):
                cell["note"] = fig["note"]
            regions[fig["bucket"]] = cell
        elif fig["kind"] == "segment":
            seg = {"name": fig["label"]}
            if fig.get("quote"):
                seg["q"] = fig["quote"]
            if is_num(fig.get("v")):
                seg["g"] = fig["v"]
            if is_num(fig.get("rev")):
                seg["rev"] = fig["rev"]
            segments.append(seg)
    if regions:
        company.setdefault("regions", {})[quarter] = regions
    if segments:
        company.setdefault("segments", {})[quarter] = segments
    if draft.get("china"):
        company["china"] = draft["china"]
    if draft.get("guidance"):
        company["guidance"] = {"kind": "testable" if draft.get("guidance_numeric") else "qualitative",
                               "date": source["date"], "text": draft["guidance"], "evidence": "",
                               "read": "Not yet assessed." if draft.get("guidance_numeric") else "Nothing to test against."}
    company["checks"] = {"ok": draft["checks"]["ok"], "total": draft["checks"]["total"]}
    if quarter > dataset.get("latest", ""):
        dataset["latest"] = quarter
    return company
