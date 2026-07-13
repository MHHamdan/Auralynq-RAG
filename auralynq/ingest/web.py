"""Web page fetching + main-content extraction for URL ingestion.

Fetches a URL safely (SSRF-guarded: private/loopback/link-local/cloud-metadata
hosts are refused, and every redirect hop is re-validated), extracts the main
article text (trafilatura when available, else a BeautifulSoup readability
heuristic), and returns it with provenance — the final URL after redirects, the
title/byline, a fetch timestamp, and a content hash for re-crawl idempotency.
"""

from __future__ import annotations

import datetime as _dt
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse

from auralynq.telemetry import get_logger
from auralynq.utils import content_hash

_log = get_logger("auralynq.web")

DEFAULT_UA = "AuralynqBot/0.2 (+https://github.com/MHHamdan/Auralynq)"
MAX_BYTES = 5_000_000
TIMEOUT_S = 15.0
MAX_REDIRECTS = 5


class WebFetchError(Exception):
    """Raised for any refused/failed fetch; carries a user-safe message."""


@dataclass
class WebPage:
    url: str  # final URL after redirects
    requested_url: str
    title: str
    text: str
    byline: str | None = None
    site_name: str | None = None
    fetched_at: str = field(default_factory=lambda: _dt.datetime.now(tz=_dt.UTC).isoformat())
    content_hash: str = ""

    def provenance(self) -> dict[str, str]:
        p = {
            "kind": "web",
            "url": self.url,
            "requested_url": self.requested_url,
            "fetched_at": self.fetched_at,
        }
        if self.byline:
            p["byline"] = self.byline
        if self.site_name:
            p["site_name"] = self.site_name
        return p


# ── SSRF safety ────────────────────────────────────────────────────────────


def _host_is_public(host: str, *, allow_private: bool) -> bool:
    """True when every resolved address for `host` is a public, routable IP."""
    if allow_private:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(str(ip).split("%")[0])  # strip zone id
        except ValueError:
            return False
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False
        # AWS/GCP/Azure link-local metadata endpoint
        if str(addr) == "169.254.169.254":
            return False
    return True


def _validate_url(url: str, *, allow_private: bool) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise WebFetchError(
            f"Only http(s) URLs are supported (got {parsed.scheme or 'no scheme'})."
        )
    host = parsed.hostname
    if not host:
        raise WebFetchError("URL has no host.")
    if not _host_is_public(host, allow_private=allow_private):
        raise WebFetchError(
            f"Refusing to fetch a non-public host ({host}) — blocked to prevent SSRF."
        )


# ── content extraction ─────────────────────────────────────────────────────


def _extract_trafilatura(html: str, url: str) -> tuple[str, str | None, str | None] | None:
    try:
        import trafilatura  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        text = trafilatura.extract(html, url=url, include_comments=False, favor_precision=True)
        if not text or len(text.strip()) < 40:
            return None
        title = byline = None
        try:
            meta = trafilatura.extract_metadata(html)
            if meta:
                title = meta.title
                byline = meta.author
        except Exception:
            pass
        return text.strip(), title, byline
    except Exception:
        return None


def _extract_bs4(html: str) -> tuple[str, str | None, str | None]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml" if _has_lxml() else "html.parser")

    # meta title/author before we strip anything
    title = None
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = str(og["content"]).strip()
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    byline = None
    author = soup.find("meta", attrs={"name": "author"}) or soup.find(
        "meta", property="article:author"
    )
    if author and author.get("content"):
        byline = str(author["content"]).strip()

    # strip non-content chrome
    for tag in soup(
        ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg"]
    ):
        tag.decompose()

    # prefer semantic main content; else the densest block
    candidates = soup.find_all(["article", "main"]) or soup.find_all(["div", "section"])
    best = None
    best_len = 0
    for node in candidates:
        text = node.get_text(" ", strip=True)
        if len(text) > best_len:
            best, best_len = node, len(text)
    root = best or soup.body or soup

    # keep block structure: paragraphs / headings / list items on their own lines
    parts: list[str] = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre"]):
        t = el.get_text(" ", strip=True)
        if t:
            parts.append(t)
    text = "\n\n".join(parts) if parts else root.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, title, byline


def _has_lxml() -> bool:
    import importlib.util

    return importlib.util.find_spec("lxml") is not None


def fetch_url(
    url: str,
    *,
    timeout: float = TIMEOUT_S,
    max_bytes: int = MAX_BYTES,
    user_agent: str = DEFAULT_UA,
    allow_private: bool = False,
) -> WebPage:
    """Fetch `url` and return the extracted main content + provenance.

    Raises WebFetchError on a refused host, non-HTML content, oversized body, or
    empty extraction.
    """
    import httpx

    requested = url.strip()
    _validate_url(requested, allow_private=allow_private)

    headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"}
    current = requested
    html = ""
    final_url = requested
    with httpx.Client(follow_redirects=False, timeout=timeout, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _validate_url(current, allow_private=allow_private)  # re-check every hop
            resp = client.get(current)
            if resp.is_redirect:
                loc = resp.headers.get("location")
                if not loc:
                    break
                current = str(httpx.URL(current).join(loc))
                continue
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "xml" not in ctype and not ctype.startswith("text/"):
                raise WebFetchError(
                    f"Unsupported content type '{ctype or 'unknown'}' — expected HTML."
                )
            raw = resp.content[: max_bytes + 1]
            if len(raw) > max_bytes:
                raise WebFetchError(f"Page exceeds the {max_bytes // 1_000_000} MB limit.")
            html = raw.decode(resp.encoding or "utf-8", errors="replace")
            final_url = str(resp.url)
            break
        else:
            raise WebFetchError("Too many redirects.")

    if not html:
        raise WebFetchError("Empty response body.")

    extracted = _extract_trafilatura(html, final_url) or _extract_bs4(html)
    text, title, byline = extracted
    if not text or len(text.strip()) < 40:
        raise WebFetchError("Could not extract meaningful text from the page.")

    site = urlparse(final_url).hostname
    page = WebPage(
        url=final_url,
        requested_url=requested,
        title=(title or site or final_url).strip()[:300],
        text=text.strip(),
        byline=byline,
        site_name=site,
        content_hash=content_hash(text.strip()),
    )
    _log.info("web.fetched", url=final_url, chars=len(page.text), title=page.title[:80])
    return page
