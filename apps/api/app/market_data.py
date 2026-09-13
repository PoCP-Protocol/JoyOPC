from __future__ import annotations

from dataclasses import dataclass
from typing import Any


GEO_MAP = {"US": "US", "UK": "GB", "SG": "SG", "JP": "JP", "DE": "DE", "FR": "FR", "CA": "CA", "AU": "AU"}


@dataclass(slots=True)
class GoogleTrendsAdapter:
    """Live public market-interest adapter.

    Uses pytrends as a best-effort public Google Trends client. It is intentionally isolated
    behind this adapter because Google does not provide a stable public Trends API contract.
    """

    market: str = "US"

    def pull(self, keywords: list[str]) -> list[dict[str, Any]]:
        try:
            from pytrends.request import TrendReq
        except ImportError as exc:
            raise RuntimeError("pytrends is not installed") from exc
        if not keywords:
            return []
        pytrends = TrendReq(hl="en-US", tz=0)
        geo = GEO_MAP.get(self.market.upper(), self.market.upper())
        results: list[dict[str, Any]] = []
        for start in range(0, len(keywords), 5):
            chunk = keywords[start : start + 5]
            pytrends.build_payload(chunk, timeframe="today 3-m", geo=geo)
            df = pytrends.interest_over_time()
            if df.empty:
                continue
            for kw in chunk:
                if kw not in df:
                    continue
                series = df[kw].astype(float)
                current = float(series.tail(min(7, len(series))).mean())
                previous = float(series.iloc[-14:-7].mean()) if len(series) >= 14 else float(series.head(max(1, len(series) // 2)).mean())
                delta = current - previous
                growth = max(0.0, min(100.0, 50.0 + delta))
                results.append({
                    "source": "Google Trends Live",
                    "market": self.market.upper(),
                    "channel": "SEARCH",
                    "keyword": kw,
                    "demand_score": round(current, 1),
                    "growth_score": round(growth, 1),
                    "social_velocity": 50.0,
                    "competition_score": 50.0,
                    "median_price": 0.0,
                    "confidence": 78.0,
                })
        return results
