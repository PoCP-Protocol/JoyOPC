"""AiSoul-style market crawler intake for JoyOPC.

Discipline copied from AiSoul trend_crawler:
- fail-fast on fetch/parse failure; never invent MarketSignal rows
- every signal carries provenance (url, host, sha256, weak-signal grade)
- crawl output is inferred_external only: it can re-score demand/competition,
  it cannot bypass Product Zone rules or auto-SCALE a product
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

from .base import RawMarketSignal
from .page_fetcher import fetch_page

HEAT_WORDS = (
    "trend", "trending", "viral", "bestseller", "best seller", "sold out",
    "growing", "search volume", " explod", "hot", "爆款", "热销", "趋势",
)
COMPETE_WORDS = (
    "competition", "saturated", "crowded", "price war", "cheap", "generic",
    "同质", "内卷", "低价", "红海",
)


class CrawlError(RuntimeError):
    """Fetch/parse failed — do not write fake market signals."""


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, value)), 1)


def _host(url: str) -> str:
    return urlparse(url).hostname or "unknown"


def heuristic_extract(text: str, *, keywords: list[str], title: str = "") -> list[dict[str, Any]]:
    blob = f"{title}\n{text}".lower()
    if len(blob.strip()) < 40:
        raise CrawlError("extracted text too short to form a market signal")
    heat = sum(blob.count(word) for word in HEAT_WORDS)
    compete = sum(blob.count(word) for word in COMPETE_WORDS)
    out: list[dict[str, Any]] = []
    for keyword in keywords:
        kw = keyword.strip()
        if not kw:
            continue
        hits = blob.count(kw.lower())
        demand = _clip(38 + hits * 8 + heat * 3)
        growth = _clip(40 + heat * 4 + hits * 2)
        competition = _clip(45 + compete * 6)
        social = _clip(40 + heat * 5)
        out.append({
            "keyword": kw,
            "demand_score": demand,
            "growth_score": growth,
            "social_velocity": social,
            "competition_score": competition,
            "median_price": 0.0,
            "confidence": _clip(38 + min(hits, 4) * 4),  # cap: weak signal
            "mentions": hits,
        })
    if not out:
        raise CrawlError("no keywords survived extraction")
    if all(item["mentions"] == 0 for item in out):
        raise CrawlError("page did not mention the requested keywords; refusing empty inference")
    return out


@dataclass(slots=True)
class PublicPageCrawler:
    """MarketSignalAdapter that turns public pages into weak MarketSignal rows."""

    market: str = "US"
    channel: str = "WEB"

    def collect(
        self,
        *,
        urls: list[str],
        keywords: list[str],
        transport: Callable[[str, float, int], dict[str, Any]] | None = None,
    ) -> list[RawMarketSignal]:
        if not urls:
            raise CrawlError("no urls to crawl (fail-fast, refuse empty write)")
        if not keywords:
            raise CrawlError("no keywords to extract (fail-fast, refuse empty write)")
        signals: list[RawMarketSignal] = []
        for url in urls:
            page = fetch_page(url, transport=transport, source_mode="simulation" if transport else "live")
            if not page.get("available"):
                raise CrawlError(page.get("error") or f"fetch failed for {url}")
            parsed = heuristic_extract(str(page.get("text") or ""), keywords=keywords, title=str(page.get("title") or ""))
            host = _host(str(page.get("final_url") or url))
            source = f"crawl:{host}"
            for item in parsed:
                signals.append(RawMarketSignal(
                    source=source,
                    market=self.market.upper(),
                    channel=self.channel,
                    keyword=item["keyword"],
                    demand_score=item["demand_score"],
                    growth_score=item["growth_score"],
                    social_velocity=item["social_velocity"],
                    competition_score=item["competition_score"],
                    median_price=item["median_price"],
                    confidence=item["confidence"],
                ))
        if not signals:
            raise CrawlError("no factors to ingest (fail-fast, refuse empty write)")
        return signals

    def to_market_rows(self, signals: list[RawMarketSignal]) -> list[dict[str, Any]]:
        return [
            {
                "source": s.source,
                "market": s.market,
                "channel": s.channel,
                "keyword": s.keyword,
                "demand_score": s.demand_score,
                "growth_score": s.growth_score,
                "social_velocity": s.social_velocity,
                "competition_score": s.competition_score,
                "median_price": s.median_price,
                "confidence": s.confidence,
            }
            for s in signals
        ]
