from __future__ import annotations

from typing import Any, Iterable

# Strategy names borrowed from KubeRiva/OMS. Scoring is JoyOPC-owned and uses
# SupplierProduct cost / lead time / exclusive rights — we do not run KubeRiva.

STRATEGIES = (
    "COST_OPTIMAL",
    "LEAD_TIME_OPTIMAL",
    "EXCLUSIVE_PREFERRED",
    "BALANCED",
    "AI_ADAPTIVE",
)


def score_supplier_nodes(
    *,
    strategy: str,
    nodes: Iterable[dict[str, Any]],
    uniqueness: float = 50,
    content_advantage: float = 50,
) -> list[dict[str, Any]]:
    wanted = (strategy or "BALANCED").upper()
    if wanted not in STRATEGIES:
        wanted = "BALANCED"
    ranked: list[dict[str, Any]] = []
    for node in nodes:
        cost = float(node.get("supplier_price") or node.get("landed_cost") or 0)
        lead = float(node.get("lead_time_days") or 14)
        exclusive = bool(node.get("exclusive_rights"))
        moq = float(node.get("moq") or 1)
        cost_score = max(0.0, 100 - cost)
        speed_score = max(0.0, 100 - lead * 4)
        exclusive_score = 90.0 if exclusive else 40.0
        moq_score = 80.0 if moq <= 5 else 45.0
        if wanted == "COST_OPTIMAL":
            score = 0.7 * cost_score + 0.2 * speed_score + 0.1 * moq_score
        elif wanted == "LEAD_TIME_OPTIMAL":
            score = 0.7 * speed_score + 0.2 * cost_score + 0.1 * exclusive_score
        elif wanted == "EXCLUSIVE_PREFERRED":
            score = 0.55 * exclusive_score + 0.25 * cost_score + 0.2 * speed_score
        elif wanted == "AI_ADAPTIVE":
            score = 0.3 * cost_score + 0.2 * speed_score + 0.2 * exclusive_score + 0.15 * uniqueness + 0.15 * content_advantage
        else:
            score = 0.35 * cost_score + 0.25 * speed_score + 0.25 * exclusive_score + 0.15 * moq_score
        ranked.append({**node, "strategy": wanted, "sourcing_score": round(score, 2)})
    ranked.sort(key=lambda row: row["sourcing_score"], reverse=True)
    return ranked
