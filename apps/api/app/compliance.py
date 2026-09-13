from __future__ import annotations

import re
from typing import Any

from app.product_unit import BATTERY_CERTS, ProductUnit, parse_json_list

# Character/IP tokens that must not SCALE without exclusive_rights or character_ip_cleared.
BRANDED_IP_RE = re.compile(
    r"\b(disney|marvel|pokemon|pokémon|pikachu|elsa|frozen|mickey|minnie|hello\s*kitty|"
    r"labubu|popmart|pop\s*mart|spiderman|spider-man|batman|star\s*wars|lego\b|"
    r"peppa|cocomelon|paw\s*patrol|transformers)\b",
    re.I,
)

AGE_DEFAULT = "3+"
MANUAL_LANG = {
    "US": ["en"],
    "UK": ["en"],
    "EU": ["en", "de", "fr"],
    "SG": ["en", "zh"],
    "JP": ["ja", "en"],
}

WARNING_TEMPLATES = [
    "Not suitable for children under {age} years. Small parts. Choking hazard.",
    "Adult supervision required during play.",
    "Do not expose the battery to heat, fire, or puncture.",
    "This toy uses on-device responses; do not present it as an unrestricted cloud companion.",
]


def branded_character_hit(name: str) -> str | None:
    match = BRANDED_IP_RE.search(name or "")
    return match.group(0) if match else None


def apply_ip_hard_gate(*, product_name: str, exclusive_rights: bool, character_ip_cleared: bool, zone: str, decision: str) -> dict[str, Any]:
    hit = branded_character_hit(product_name)
    if not hit:
        return {"zone": zone, "decision": decision, "hit": None, "reasons": [], "actions": []}
    if exclusive_rights or character_ip_cleared:
        return {
            "zone": zone,
            "decision": decision,
            "hit": hit,
            "reasons": [f"名称含品牌/角色「{hit}」，已标记授权或 IP 清除。"],
            "actions": ["上架前把授权范围、期限、渠道写进合同附件"],
        }
    reasons = [f"IP硬闸：名称含「{hit}」且无独家授权/IP清除，禁止独占与放量。"]
    actions = ["无授权角色玩具不得 SCALE；改为自有人设或取得书面授权后再评估"]
    decision = "REJECT" if decision == "SCALE" else ("HOLD" if decision == "TEST" else decision)
    if decision not in {"HOLD", "REJECT"}:
        decision = "HOLD"
    return {"zone": "HOMOGENEOUS", "decision": decision, "hit": hit, "reasons": reasons, "actions": actions}


def compliance_passport(unit: ProductUnit, *, product_name: str = "", age_grade: str = AGE_DEFAULT) -> dict[str, Any]:
    market = (unit.market or "US").upper()
    gap = unit.cert_gap()
    claimed = {f.lower() for f in unit.claimed_features}
    battery = "battery" in claimed or "wireless" in claimed
    warnings = [w.format(age=age_grade.replace("+", "")) for w in WARNING_TEMPLATES]
    return {
        "product_name": product_name,
        "age_grade": age_grade,
        "destination_market": market,
        "certs_required": unit.required_certs(),
        "certs_held": list(unit.certs_held),
        "cert_gap": gap,
        "cert_ok": not gap,
        "battery_air": {
            "required": battery,
            "docs": list(BATTERY_CERTS) if battery else [],
            "ready": all(c.upper() in {x.upper() for x in unit.certs_held} for c in BATTERY_CERTS) if battery else True,
        },
        "warnings": warnings,
        "manual_languages": MANUAL_LANG.get(market, ["en"]),
        "listing_claim_limits": [
            "Do not claim unrestricted cloud AI conversation.",
            "Do not claim medical / educational outcome without evidence.",
        ],
        "publish_rule": "cert_ok 之前只允许 DRAFT；无授权角色 IP 不得 SCALE",
    }


def passport_from_orm(obj: Any) -> dict[str, Any]:
    from app.product_unit import unit_from_orm

    unit = unit_from_orm(obj)
    return compliance_passport(unit, product_name=getattr(obj, "name", "") or getattr(obj, "product_name", ""))
