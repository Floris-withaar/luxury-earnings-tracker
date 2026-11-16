"""Download a release and turn it into plain text (HTML or PDF).

Two guards sit in front of every download:
  is_trusted    the link is on the allowlist: a watchlist company's own site or a regulatory wire
  check_public  the link points at the public internet, never at a private or local address
"""
from __future__ import annotations

import io
import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urljoin, urlparse

MAX_BYTES = 25 * 1024 * 1024
MAX_CHARS = 150_000
MAX_REDIRECTS = 5
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; luxury-earnings-tracker/1.0; research use)",
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en",
}

# Regulatory wires and exchange sites that carry unedited company releases.
TRUSTED_WIRES = [
    "globenewswire.com", "businesswire.com", "prnewswire.com", "live.euronext.com", "mfn.se",
    "emarketstorage.it", "londonstockexchange.com", "hkexnews.hk", "six-group.com", "sec.gov",
]


class UntrustedSource(ValueError):
    """The link is not allowed: wrong scheme, a private address, or off the allowlist."""


class FetchFailed(RuntimeError):
    """The site did not hand over the document. The message says what it answered."""


def allowlist(watchlist: dict | None) -> list[str]:
    domains = [c["ir_domain"].lower() for c in (watchlist or {}).get("companies", []) if c.get("ir_domain")]
    return sorted(set(domains + TRUSTED_WIRES))


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_trusted(url: str, domains: list[str]) -> bool:
    """True when the link's host is an allowlisted domain or a subdomain of one."""
    if urlparse(url).scheme != "https":
        return False
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in domains)


def check_public(url: str) -> None:
    """Refuse anything that is not a plain web link to a public address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UntrustedSource("Only http and https links are fetched.")
    host = parsed.hostname or ""
    if not host or host == "localhost" or host.endswith((".local", ".internal")):
        raise UntrustedSource(f"{host or 'This link'} is not a public address.")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, None)]
        except socket.gaierror as exc:
            raise UntrustedSource(f"{host} could not be resolved.") from exc
    if any(not a.is_global for a in addresses):
        raise UntrustedSource(f"{host} resolves to a private or local address.")


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
    """Download a link and return its text. Every redirect hop is checked like the first link."""
    import requests

    for _ in range(MAX_REDIRECTS + 1):
        check_public(url)
        response = requests.get(url, headers=HEADERS, timeout=40, allow_redirects=False, stream=True)
        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, response.headers.get("location", ""))
            continue
        if response.status_code >= 400:
            # Many investor sites turn away automated readers with 403. That is theirs to decide:
            # the release then goes in by hand with `add --file`.
            raise FetchFailed(f"{host_of(url)} answered HTTP {response.status_code}")
        raw = response.raw.read(MAX_BYTES, decode_content=True)
        return text_from_bytes(raw, response.headers.get("content-type", ""), url.split("?")[0])
    raise UntrustedSource("Too many redirects.")


def read_file(path: str) -> str:
    p = Path(path)
    return text_from_bytes(p.read_bytes(), "", p.name)
