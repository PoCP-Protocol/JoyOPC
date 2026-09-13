from __future__ import annotations

import re
from typing import Iterable

# Inspired by lien0219/trademind-ai SKU binding: exact → normalized → similar; never guess at low confidence.


def normalize_sku(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def match_master_sku(query: str, catalog: Iterable[tuple[str, str]], *, min_score: float = 0.72) -> dict:
    raw = (query or "").strip()
    if not raw:
        return {"sku": "", "score": 0.0, "method": "UNMATCHED", "candidates": []}
    items = list(catalog)
    nq = normalize_sku(raw)
    qlow = raw.lower()

    for sku, _name in items:
        if sku.upper() == raw.upper():
            return {"sku": sku, "score": 1.0, "method": "EXACT", "candidates": []}
    for sku, _name in items:
        if nq and normalize_sku(sku) == nq:
            return {"sku": sku, "score": 0.95, "method": "NORMALIZED", "candidates": []}

    scored: list[tuple[float, str, str]] = []
    for sku, name in items:
        blob = f"{sku} {name}".lower()
        if qlow in blob or normalize_sku(name) and nq and nq in normalize_sku(name):
            score = 0.82 if qlow in blob else 0.74
            scored.append((score, sku, name))
        elif nq and nq in normalize_sku(sku):
            scored.append((0.78, sku, name))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < min_score:
        return {
            "sku": "",
            "score": scored[0][0] if scored else 0.0,
            "method": "UNMATCHED",
            "candidates": [{"sku": sku, "name": name, "score": score} for score, sku, name in scored[:5]],
        }
    best_score, sku, _name = scored[0]
    if len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 0.03:
        return {
            "sku": "",
            "score": best_score,
            "method": "AMBIGUOUS",
            "candidates": [{"sku": s, "name": n, "score": sc} for sc, s, n in scored[:5]],
        }
    return {"sku": sku, "score": best_score, "method": "SIMILAR", "candidates": []}
