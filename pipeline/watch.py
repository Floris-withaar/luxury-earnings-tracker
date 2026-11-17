"""The weekly watch. Looks for anything a person should know about and writes it up.

It needs no API key. It checks four things:
  1. the data gate: errors, and releases that are overdue
  2. every source link: a link that has gone (404, 410, or a name that no longer resolves)
  3. drafts waiting in data/review
  4. the results of an update run, when a report file is passed in

    python -m pipeline.run watch --report watch.md      exits 10 when something needs attention

The workflow turns a non-empty report into a GitHub issue assigned to the repository owner,
which GitHub emails. One issue stays open and collects comments until the watch is clean again.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import fetch, validate
from .common import REVIEW

GONE = (404, 410)


def link_status(url: str) -> tuple[str, str]:
    """Returns (state, detail). state is ok, gone, refused or unknown. Only gone is an alert."""
    import requests

    try:
        fetch.check_public(url)
        response = requests.get(url, headers=fetch.HEADERS, timeout=25, stream=True, allow_redirects=True)
        response.close()
    except fetch.UntrustedSource as exc:
        return ("gone" if "could not be resolved" in str(exc) else "unknown", str(exc))
    except Exception as exc:   # a timeout or a dropped connection says nothing about the link
        return "unknown", type(exc).__name__
    code = response.status_code
    if code in GONE:
        return "gone", f"HTTP {code}"
    if code < 400:
        return "ok", f"HTTP {code}"
    # 401, 403 and 429 mean the site turns automated readers away. The link still works in a browser.
    return ("refused" if code in (401, 403, 429) else "unknown"), f"HTTP {code}"


def check_links(dataset: dict, status=link_status) -> list[dict]:
    """One entry per source link that has gone."""
    links = [(c["name"], s) for c in dataset.get("companies", []) for s in (c.get("sources") or []) if s.get("url")]
    with ThreadPoolExecutor(max_workers=8) as pool:
        states = list(pool.map(lambda item: status(item[1]["url"]), links))
    return [{"company": name, "title": s["t"], "url": s["url"], "detail": detail}
            for (name, s), (state, detail) in zip(links, states) if state == "gone"]


def waiting_drafts() -> list[str]:
    return sorted(p.name for p in REVIEW.glob("*.json")) if REVIEW.exists() else []


def watch(dataset: dict, watchlist: dict | None, *, today: date | None = None, links: bool = True, status=link_status) -> dict:
    gate = validate.validate(dataset, watchlist, today=today)
    alerts = [f"Data gate error: {e}" for e in gate["errors"] + validate.check_built(dataset)]
    alerts += [f"Overdue: {a}" for a in gate["alerts"]]
    alerts += [f"Draft waiting for review: data/review/{name}" for name in waiting_drafts()]
    notes = [w for w in gate["warnings"] if w not in gate["alerts"]]
    if links:
        gone = check_links(dataset, status)
        total = sum(1 for c in dataset.get("companies", []) for s in (c.get("sources") or []) if s.get("url"))
        # Links do not all die in one week. If a third of them seem gone, the fault is in the network this ran on.
        if total and len(gone) > max(3, total // 3):
            notes.append(f"The link check found {len(gone)} of {total} links unreachable at once, which points to a network fault. It will run again next week.")
        else:
            alerts += [f"Source link has gone ({x['detail']}): {x['company']}, {x['title']}. {x['url']}" for x in gone]
    return {"alerts": alerts, "notes": notes, "figures": gate["figures"], "companies": gate["companies"]}


def markdown(result: dict, extra: list[str] | None = None, run_url: str | None = None) -> str:
    """The report as it appears in the issue. Empty when there is nothing to say."""
    alerts = result["alerts"] + (extra or [])
    if not alerts:
        return ""
    lines = [f"The weekly watch found {len(alerts)} thing{'s' if len(alerts) != 1 else ''} that need{'' if len(alerts) != 1 else 's'} a person.", ""]
    lines += [f"- {a}" for a in alerts]
    if result["notes"]:
        lines += ["", "Standing notes, for information:"] + [f"- {n}" for n in result["notes"]]
    lines += ["", f"Checked {result['figures']} figures across {result['companies']} companies."]
    if run_url:
        lines += [f"Run: {run_url}"]
    lines += ["", "What to do: see the section \"How you hear about problems\" in the README."]
    return "\n".join(lines) + "\n"
