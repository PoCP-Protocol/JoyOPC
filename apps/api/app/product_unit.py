"""AI toy ProductUnit passport — soul × module × shell, absorbed from JoySoul.

Deterministic gates only. LLM does not decide zone or cert.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

GEN1_FEATURES = frozenset({"mic", "speaker", "network", "wireless", "battery"})
GEN2_FEATURES = GEN1_FEATURES | {"camera"}
GEN3_FEATURES = GEN2_FEATURES | {"limb", "servo", "expression"}
GEN4_FEATURES = GEN3_FEATURES | {"locomotion"}

CERTIFIED_BY_GEN = {
    1: GEN1_FEATURES,
    2: GEN2_FEATURES,
    3: GEN3_FEATURES,
    4: GEN4_FEATURES,
}

MARKET_REQUIRED_CERTS = {
    "US": ("CPC", "ASTM", "CPSIA"),
    "UK": ("UKCA", "EN71", "REACH"),
    "EU": ("EN71", "CE", "REACH"),
    "CA": ("CCPSA",),
    "AU": ("AS/NZS", "ISO8124"),
    "CN": ("CCC",),
    "SG": ("EN71", "CE"),
}

BATTERY_CERTS = ("UN38.3", "MSDS")
US_BASELINE_CERTS = list(MARKET_REQUIRED_CERTS["US"])

ORM_UNIT_FIELDS = (
    "soul_recipe_id",
    "has_persona",
    "memory_enabled",
    "skills_json",
    "hw_gen",
    "module_tier",
    "shell",
    "claimed_features_json",
    "certs_held_json",
    "cert_gap_json",
    "needs_hardware_gate",
)

PAYLOAD_LIST_KEYS = ("skills", "claimed_features", "certs_held")


def parse_json_list(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    if text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = []
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def dump_json_list(values: Iterable[str]) -> str:
    return json.dumps(parse_json_list(list(values)), ensure_ascii=False)


@dataclass(slots=True)
class ProductUnit:
    soul_recipe_id: str = ""
    has_persona: bool = False
    memory_enabled: bool = False
    skills: list[str] = field(default_factory=list)
    hw_gen: int = 1
    module_tier: str = "Mini"
    shell: str = ""
    claimed_features: list[str] = field(default_factory=list)
    certs_held: list[str] = field(default_factory=list)
    market: str = "US"

    @property
    def has_companion_soul(self) -> bool:
        return bool(self.has_persona and self.memory_enabled)

    @property
    def hw_gen_clamped(self) -> int:
        return min(4, max(1, int(self.hw_gen or 1)))

    def certified_features(self) -> frozenset[str]:
        return CERTIFIED_BY_GEN[self.hw_gen_clamped]

    def excess_features(self) -> list[str]:
        allowed = self.certified_features()
        return sorted({f.lower() for f in self.claimed_features if f.lower() not in allowed})

    def required_certs(self) -> list[str]:
        market = (self.market or "US").upper()
        if market in {"DE", "FR", "IT", "ES", "NL"}:
            market = "EU"
        required = list(MARKET_REQUIRED_CERTS.get(market, MARKET_REQUIRED_CERTS["US"]))
        claimed = {f.lower() for f in self.claimed_features}
        if "battery" in claimed or "wireless" in claimed:
            required.extend(BATTERY_CERTS)
        return required

    def cert_gap(self) -> list[str]:
        held = {c.upper() for c in self.certs_held}
        return [c for c in self.required_certs() if c.upper() not in held]

    def needs_hardware_gate(self) -> bool:
        return bool(self.excess_features())

    def to_selection_fields(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "soul_recipe_id": self.soul_recipe_id,
            "has_persona": self.has_persona,
            "memory_enabled": self.memory_enabled,
            "skills": list(self.skills),
            "hw_gen": self.hw_gen_clamped,
            "module_tier": self.module_tier,
            "shell": self.shell,
            "claimed_features": list(self.claimed_features),
            "certs_held": list(self.certs_held),
        }

    def to_orm_fields(self, *, cert_gap: list[str] | None = None, hardware_gate: bool | None = None) -> dict[str, Any]:
        return {
            "soul_recipe_id": self.soul_recipe_id or "",
            "has_persona": bool(self.has_persona),
            "memory_enabled": bool(self.memory_enabled),
            "skills_json": dump_json_list(self.skills),
            "hw_gen": self.hw_gen_clamped,
            "module_tier": self.module_tier or "Mini",
            "shell": self.shell or "",
            "claimed_features_json": dump_json_list(self.claimed_features),
            "certs_held_json": dump_json_list(self.certs_held),
            "cert_gap_json": dump_json_list(self.cert_gap() if cert_gap is None else cert_gap),
            "needs_hardware_gate": self.needs_hardware_gate() if hardware_gate is None else bool(hardware_gate),
        }

    def to_api_dict(self, *, cert_gap: list[str] | None = None, hardware_gate: bool | None = None) -> dict[str, Any]:
        gap = self.cert_gap() if cert_gap is None else cert_gap
        gate = self.needs_hardware_gate() if hardware_gate is None else hardware_gate
        return {
            "soul_recipe_id": self.soul_recipe_id or "",
            "has_persona": bool(self.has_persona),
            "memory_enabled": bool(self.memory_enabled),
            "has_companion_soul": self.has_companion_soul,
            "skills": parse_json_list(self.skills),
            "hw_gen": self.hw_gen_clamped,
            "module_tier": self.module_tier or "Mini",
            "shell": self.shell or "",
            "claimed_features": parse_json_list(self.claimed_features),
            "certs_held": parse_json_list(self.certs_held),
            "cert_gap": gap,
            "needs_hardware_gate": bool(gate),
            "cert_ok": not gap,
        }


def companion_passport(
    *,
    soul_recipe_id: str,
    shell: str,
    skills: list[str] | None = None,
    module_tier: str = "Mini",
    hw_gen: int = 1,
    claimed_features: list[str] | None = None,
    certs_held: list[str] | None = None,
    market: str = "US",
) -> ProductUnit:
    return ProductUnit(
        soul_recipe_id=soul_recipe_id,
        has_persona=True,
        memory_enabled=True,
        skills=skills or ["睡前故事", "情绪安抚"],
        hw_gen=hw_gen,
        module_tier=module_tier,
        shell=shell,
        claimed_features=claimed_features or ["mic", "speaker", "network"],
        certs_held=certs_held if certs_held is not None else list(US_BASELINE_CERTS),
        market=market,
    )


def unit_from_mapping(data: dict[str, Any] | None, *, market: str = "US") -> ProductUnit:
    data = data or {}
    return ProductUnit(
        soul_recipe_id=str(data.get("soul_recipe_id") or ""),
        has_persona=bool(data.get("has_persona")),
        memory_enabled=bool(data.get("memory_enabled")),
        skills=parse_json_list(data.get("skills", data.get("skills_json"))),
        hw_gen=int(data.get("hw_gen") or 1),
        module_tier=str(data.get("module_tier") or "Mini"),
        shell=str(data.get("shell") or ""),
        claimed_features=parse_json_list(data.get("claimed_features", data.get("claimed_features_json"))),
        certs_held=parse_json_list(data.get("certs_held", data.get("certs_held_json"))),
        market=str(data.get("market") or market or "US"),
    )


def unit_from_orm(obj: Any, *, market: str | None = None) -> ProductUnit:
    return ProductUnit(
        soul_recipe_id=getattr(obj, "soul_recipe_id", "") or "",
        has_persona=bool(getattr(obj, "has_persona", False)),
        memory_enabled=bool(getattr(obj, "memory_enabled", False)),
        skills=parse_json_list(getattr(obj, "skills_json", "[]")),
        hw_gen=int(getattr(obj, "hw_gen", 1) or 1),
        module_tier=getattr(obj, "module_tier", None) or "Mini",
        shell=getattr(obj, "shell", None) or "",
        claimed_features=parse_json_list(getattr(obj, "claimed_features_json", "[]")),
        certs_held=parse_json_list(getattr(obj, "certs_held_json", "[]")),
        market=market or getattr(obj, "market", None) or getattr(obj, "target_market", None) or "US",
    )


def apply_unit_to_orm(obj: Any, unit: ProductUnit) -> None:
    for key, value in unit.to_orm_fields().items():
        setattr(obj, key, value)


def copy_unit(src: Any, dest: Any) -> None:
    for key in ORM_UNIT_FIELDS:
        setattr(dest, key, getattr(src, key))


def candidate_orm_kwargs(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    unit = unit_from_mapping(data, market=str(data.get("market") or "US"))
    for key in PAYLOAD_LIST_KEYS:
        data.pop(key, None)
    data.pop("cert_gap", None)
    data.pop("needs_hardware_gate", None)
    data.update(unit.to_orm_fields())
    return data


def unit_api_dict(obj: Any, *, market: str | None = None) -> dict[str, Any]:
    unit = unit_from_orm(obj, market=market)
    return unit.to_api_dict(
        cert_gap=parse_json_list(getattr(obj, "cert_gap_json", "[]")),
        hardware_gate=bool(getattr(obj, "needs_hardware_gate", False)),
    )


def apply_product_gates(zone: str, decision: str, unit: ProductUnit) -> dict[str, Any]:
    """Hard JoySoul rules on top of commercial three-zone scores."""
    reasons: list[str] = []
    actions: list[str] = []
    hardware_gate = unit.needs_hardware_gate()
    gap = unit.cert_gap()

    if not unit.has_companion_soul:
        if zone != "HOMOGENEOUS":
            reasons.append("无人格记忆魂，按套壳问答压入同质区。")
            actions.append("先配 SoulRecipe（人设+记忆默认关需家长授权后再开），再谈独占")
        zone = "HOMOGENEOUS"

    if hardware_gate:
        excess = "、".join(unit.excess_features())
        reasons.append(f"硬件门禁：Gen{unit.hw_gen_clamped} 已认证模组不能承诺 {excess}。")
        actions.append("降代际承诺或换已认证模组后再申请独占")
        if zone == "EXCLUSIVE":
            zone = "ADVANTAGE"

    if gap and decision == "SCALE":
        reasons.append("认证缺口未齐，不得硬件放量 SCALE：" + "、".join(gap))
        actions.append("可 TEST / DRAFT 上架；cert_ok 之前禁止真实渠道放量")
        decision = "TEST"

    return {
        "zone": zone,
        "decision": decision,
        "needs_hardware_gate": hardware_gate,
        "cert_gap": gap,
        "has_companion_soul": unit.has_companion_soul,
        "reasons": reasons,
        "recommended_actions": actions,
    }


def live_publish_block_reason(obj: Any, *, publish_as_draft: bool) -> str | None:
    if publish_as_draft:
        return None
    gap = parse_json_list(getattr(obj, "cert_gap_json", "[]"))
    if gap:
        return f"认证缺口 {', '.join(gap)}：只允许 DRAFT，不能真实渠道放量"
    return None
