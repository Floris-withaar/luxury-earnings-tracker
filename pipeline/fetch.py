"""Download a release and turn it into plain text (HTML or PDF)."""
from __future__ import annotations

import io
import re
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
MAX_CHARS = 150_000
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; luxury-earnings-tracker/1.0; research use)"}


def _pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:40])


def _html_text(raw: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text("\n")


def clean(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_CHARS]


def text_from_bytes(raw: bytes, content_type: str = "", name: str = "") -> str:
    is_pdf = raw[:5] == b"%PDF-" or "pdf" in content_type.lower() or name.lower().endswith(".pdf")
    if is_pdf:
        return clean(_pdf_text(raw))
    if "html" in content_type.lower() or name.lower().endswith((".htm", ".html")) or b"<html" in raw[:2000].lower():
        return clean(_html_text(raw))
    return clean(raw.decode("utf-8", errors="replace"))


def fetch_text(url: str) -> str:
    import requests

    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Only http and https links are fetched.")
    response = requests.get(url, headers=HEADERS, timeout=40)
    response.raise_for_status()
    raw = response.content[:MAX_BYTES]
    return text_from_bytes(raw, response.headers.get("content-type", ""), url.split("?")[0])


def read_file(path: str) -> str:
    p = Path(path)
    return text_from_bytes(p.read_bytes(), "", p.name)
