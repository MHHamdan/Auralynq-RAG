"""Web URL ingestion — SSRF guard, main-content extraction, and idempotent index.

Network-free: SSRF is tested against literal IPs (no DNS), extraction against a
static HTML string, and the full ingest with a stubbed fetcher on the offline
stack (hash embedder + memory store from conftest).
"""

from __future__ import annotations

import pytest

from auralynq.ingest.web import WebFetchError, WebPage, _extract_bs4, _validate_url


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://127.0.0.1/",
        "http://localhost/",
        "http://10.0.0.5/",
        "http://192.168.1.10/",
        "http://[::1]/",  # ipv6 loopback
        "ftp://example.com/",  # scheme allowlist
        "file:///etc/passwd",
    ],
)
def test_ssrf_and_scheme_are_blocked(url):
    with pytest.raises(WebFetchError):
        _validate_url(url, allow_private=False)


def test_private_host_allowed_when_opted_in():
    # No exception when the operator explicitly trusts internal hosts.
    _validate_url("http://192.168.1.10/", allow_private=True)


def test_extract_bs4_strips_chrome_and_keeps_article():
    html = """
    <html><head><title>My Article — Site</title>
      <meta name="author" content="Ada Lovelace">
      <meta property="og:title" content="My Article">
    </head>
    <body>
      <nav>Home About Login NAVJUNK</nav>
      <header>SITE HEADER JUNK</header>
      <article>
        <h1>My Article</h1>
        <p>Retrieval-augmented generation grounds answers in sources.</p>
        <p>Auralynq builds a compounding wiki from the knowledge graph.</p>
      </article>
      <footer>FOOTERJUNK copyright</footer>
      <script>var x = "SCRIPTJUNK";</script>
    </body></html>
    """
    text, title, byline = _extract_bs4(html)
    assert title == "My Article"
    assert byline == "Ada Lovelace"
    assert "compounding wiki" in text
    assert "grounds answers" in text
    for junk in ("NAVJUNK", "SITE HEADER JUNK", "FOOTERJUNK", "SCRIPTJUNK"):
        assert junk not in text


def test_ingest_web_page_indexes_and_is_idempotent(monkeypatch):
    from auralynq.pipeline import ingest_web_page
    from auralynq.vectorstore.factory import get_store

    page = WebPage(
        url="https://example.com/post",
        requested_url="https://example.com/post",
        title="Example Post",
        text=(
            "Ericsson announced fair and reasonable FRAND patent licensing terms. "
            "The knowledge graph links Ericsson to patents and to standards bodies. "
        )
        * 6,
        byline="Reporter",
        site_name="example.com",
        content_hash="deadbeef",
    )
    monkeypatch.setattr("auralynq.ingest.web.fetch_url", lambda *a, **k: page)

    first = ingest_web_page("https://example.com/post")
    assert first["documents"] == 1
    assert first["chunks_indexed"] > 0
    assert first["url"] == "https://example.com/post"

    store = get_store()
    chunks = store.all_chunks()
    assert chunks and all(c.source == "https://example.com/post" for c in chunks)
    # provenance + cross-source tags are attached for contradiction flagging
    assert any((c.metadata or {}).get("connector") == "web" for c in chunks)
    assert any((c.metadata or {}).get("web", {}).get("url") for c in chunks)

    # unchanged content hash → idempotent skip
    second = ingest_web_page("https://example.com/post")
    assert second["documents"] == 0 and second["skipped"] == 1 and second["unchanged"] is True
