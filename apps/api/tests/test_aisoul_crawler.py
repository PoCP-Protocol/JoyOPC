from app.adapters.market.crawler import CrawlError, PublicPageCrawler
from app.adapters.market.page_fetcher import assert_public_url, fetch_page


SAMPLE_HTML = """
<html>
<head><title>AI companion toy trend report</title></head>
<body>
  <h1>AI companion toy demand is trending</h1>
  <p>Search volume for AI companion toy is growing. TikTok videos are viral.</p>
  <p>AI learning toy remains a bestseller in the US market.</p>
</body>
</html>
"""


def fake_transport(url: str, timeout: float, max_bytes: int) -> dict:
    return {
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html; charset=utf-8",
        "content": SAMPLE_HTML.encode("utf-8"),
        "truncated": False,
    }


def test_rejects_private_urls():
    try:
        assert_public_url("http://127.0.0.1/secret")
        assert False, "expected private URL rejection"
    except ValueError:
        pass
    page = fetch_page("http://localhost/internal")
    assert page["available"] is False


def test_crawl_to_market_signals_with_injected_transport():
    crawler = PublicPageCrawler(market="US")
    signals = crawler.collect(
        urls=["https://example.com/ai-companion-toy-trend"],
        keywords=["AI companion toy", "AI learning toy"],
        transport=fake_transport,
    )
    assert len(signals) == 2
    assert signals[0].source == "crawl:example.com"
    assert signals[0].keyword == "AI companion toy"
    assert signals[0].demand_score > 40
    assert signals[0].confidence <= 55
    rows = crawler.to_market_rows(signals)
    assert rows[1]["channel"] == "WEB"


def test_fail_fast_on_missing_keywords_in_page():
    crawler = PublicPageCrawler()
    try:
        crawler.collect(
            urls=["https://example.com/ai-companion-toy-trend"],
            keywords=["unrelated nuclear submarine"],
            transport=fake_transport,
        )
        assert False, "expected CrawlError"
    except CrawlError:
        pass


def test_fail_fast_empty_urls():
    try:
        PublicPageCrawler().collect(urls=[], keywords=["toy"])
        assert False, "expected CrawlError"
    except CrawlError:
        pass
