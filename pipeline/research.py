"""Step 1. Research: an LLM with web search finds the latest results release."""
from __future__ import annotations

from datetime import date, timedelta

from . import llm
from .common import QUARTER_RE, all_quarters, shift_quarter

PROMPT = """You are a research assistant for a tracker of luxury-goods earnings.

Find the most recent quarterly sales or results press release published by {name}.

Rules:
1. Search the web. Prefer the company's own investor site ({domain}). A regulatory wire copy of the
   same release (GlobeNewswire, Euronext, Business Wire, MFN) is acceptable. News articles are not.
2. The release must report sales for a three-month period or include a table of quarterly sales.
3. calendar_quarter is the calendar quarter in which the latest three-month period ends, as YYYYQn.
   A quarter ending 30 September 2026 is 2026Q3, whatever the company calls it.
4. Give the direct URL of the release page or PDF, not a landing page.
5. If you cannot find a release newer than {known}, say so with found = false.

Reply with only one JSON object:
{{"found": boolean, "url": string or null, "title": string or null, "publisher": string or null,
  "published": "YYYY-MM-DD" or null, "period_label": string or null, "calendar_quarter": "YYYYQn" or null,
  "alternates": [string], "confidence": "high" | "medium" | "low", "why": string}}
"""


def find_release(entry: dict, known_quarter: str | None = None, *, client=None) -> dict:
    """entry is one item from config/watchlist.json."""
    prompt = PROMPT.format(
        name=entry["name"],
        domain=entry.get("ir_domain") or "its investor relations site",
        known=known_quarter or "any earlier period",
    )
    tool = dict(llm.WEB_SEARCH_TOOL, max_uses=3)
    found = llm.ask_json(prompt, step="research", client=client, tools=[tool])
    if not isinstance(found, dict):
        return {"found": False, "why": "The research answer was not a JSON object."}
    url = found.get("url")
    if not (isinstance(url, str) and url.lower().startswith(("http://", "https://"))):
        found["found"] = False
    quarter = found.get("calendar_quarter")
    if not (isinstance(quarter, str) and QUARTER_RE.match(quarter)):
        found["calendar_quarter"] = None
    return found


def quarter_end(q: str) -> date:
    year, n = int(q[:4]), int(q[5])
    month, day = [(3, 31), (6, 30), (9, 30), (12, 31)][n - 1]
    return date(year, month, day)


def due_date(entry: dict, known_quarter: str | None) -> date | None:
    """The first day worth searching for the next release.

    Companies report on a steady calendar. `lags` in the watchlist holds, per calendar quarter,
    how many days after quarter end the company reported last time. Where that is unknown,
    `first_check_days` is used. Searching before this date only costs money.
    """
    if not known_quarter:
        return None
    next_quarter = shift_quarter(known_quarter, 1)
    lag = (entry.get("lags") or {}).get(next_quarter[5], entry.get("first_check_days", 10))
    return quarter_end(next_quarter) + timedelta(days=int(lag))


def is_due(entry: dict, known_quarter: str | None, today: date | None = None) -> bool:
    due = due_date(entry, known_quarter)
    return due is None or (today or date.today()) >= due


def latest_known_quarter(company: dict | None) -> str | None:
    if not company:
        return None
    quarters = all_quarters([company])
    return quarters[-1] if quarters else None


def is_newer(found: dict, known_quarter: str | None) -> bool:
    quarter = found.get("calendar_quarter")
    if not found.get("found") or not quarter:
        return False
    return known_quarter is None or quarter > known_quarter
