from __future__ import annotations

from .product_unit import MARKET_REQUIRED_CERTS
from .schemas import MixPolicy, SelectionInput


# 跨境 AI 玩具：渠道配比不同。Amazon 价格透明，同质区更毒；TikTok 可短暂内容套利；Shopify 应偏品牌/独占。
CHANNEL_MIX_POLICY = {
    "Amazon": MixPolicy(exclusive_target_pct=30, advantage_target_pct=40, homogeneous_target_pct=30, homogeneous_alert_pct=45),
    "TikTok Shop": MixPolicy(exclusive_target_pct=15, advantage_target_pct=35, homogeneous_target_pct=50, homogeneous_alert_pct=70),
    "Shopify": MixPolicy(exclusive_target_pct=35, advantage_target_pct=40, homogeneous_target_pct=25, homogeneous_alert_pct=40),
}

MARKET_LABELS = {
    "US": "美国：CPC / ASTM / CPSIA，家长决策，退货严",
    "UK": "英国：UKCA / EN71 / REACH",
    "EU": "欧盟：CE / EN71 / REACH",
    "SG": "新加坡：EN71 / CE，作亚太试验田",
    "JP": "日本：PSE/玩具安全，内容与IP敏感",
}

# 出牌顺序：先低库存验证内容，再品牌站锁认知，最后才进比价最狠的平台。
ENTRY_SEQUENCE = [
    "TikTok Shop TEST：小库存验证内容转化，不打价格战",
    "Shopify DTC：把优质/独占做成品牌资产与复购",
    "Amazon SCALE：仅独占或可验证成本/供应优势才放量，禁止同质跟价",
]

ARCHETYPE_LABELS = {
    "COMPANION": "陪伴魂玩具（人设+记忆）",
    "LEARNING": "学习/翻译类 AI 玩具",
    "GENERIC_VOICE": "套壳语音机器人",
}


def looks_like_ai_claim(name: str) -> bool:
    text = (name or "").lower()
    return any(token in text for token in ("ai", "智能", "companion", "gpt", "llm"))


def toy_archetype(x: SelectionInput) -> str:
    if x.has_persona and x.memory_enabled:
        return "COMPANION"
    name = (x.product_name or "").lower()
    if any(token in name for token in ("learn", "translator", "tutor", "学习", "翻译")):
        return "LEARNING"
    return "GENERIC_VOICE"


def mix_policy_for_channel(channel: str) -> MixPolicy:
    return CHANNEL_MIX_POLICY.get(channel, MixPolicy())


def dest_certs(market: str) -> list[str]:
    key = (market or "US").upper()
    if key in {"DE", "FR", "IT", "ES", "NL"}:
        key = "EU"
    return list(MARKET_REQUIRED_CERTS.get(key, MARKET_REQUIRED_CERTS["US"]))


def classify_crossborder_advantage(x: SelectionInput) -> str | None:
    """AI 玩具跨境特有的伪优势：名字带 AI，没有魂，也没有授权。"""
    if looks_like_ai_claim(x.product_name) and not x.has_persona and not x.exclusive_rights:
        return "FAKE_AI_LABEL"
    return None


def sku_ops_plan(
    x: SelectionInput,
    *,
    zone: str,
    decision: str,
    channel: str = "TikTok Shop",
) -> dict:
    market = (x.market or "US").upper()
    archetype = toy_archetype(x)
    certs = dest_certs(market)
    channel = channel or "TikTok Shop"
    policy = mix_policy_for_channel(channel)
    actions: list[str] = []

    if archetype == "GENERIC_VOICE" and zone != "EXCLUSIVE":
        actions.append("套壳语音机按同质区：Amazon 不跟价；最多 TikTok 小预算测内容效率。")
    if archetype == "COMPANION":
        actions.append("陪伴魂是优质/独占的产品基本面：内容讲关系与记忆，不讲参数堆砌。")
    if looks_like_ai_claim(x.product_name) and not x.has_persona:
        actions.append("商品名含 AI 但无魂：跨境广告与 Listing 禁止 AI 伴侣承诺，避免平台与家长投诉。")
    if zone == "EXCLUSIVE":
        actions.append(f"{market} 线上授权范围写进合同：平台/期限/最低供货；MAP 价保护。")
        actions.append("出牌顺序：" + " → ".join(s.split("：")[0] for s in ENTRY_SEQUENCE))
    elif zone == "ADVANTAGE":
        if channel == "TikTok Shop" or x.content_advantage >= 70:
            actions.append("优质区主场在 TikTok：内容转化达标后再考虑 Shopify；Amazon 保持观察价。")
        else:
            actions.append("把成本/供应当成可验证优势：空运样单测退货，再决定是否 FBA。")
    else:
        actions.append("同质区跨境：设 14 天内容 ROI 与毛利退出线；FBA 备货视为高风险。")

    if x.cash_cycle_days >= 45 and zone == "HOMOGENEOUS":
        actions.append("账期/海运过长且同质：禁止压 FBA 库存，用小批量空运或淘汰。")
    actions.append(f"{market} 上架前认证：{', '.join(certs)}；缺口只允许 DRAFT。")

    return {
        "archetype": archetype,
        "archetype_label": ARCHETYPE_LABELS[archetype],
        "market": market,
        "market_note": MARKET_LABELS.get(market, MARKET_LABELS["US"]),
        "channel": channel,
        "certs_required": certs,
        "entry_sequence": ENTRY_SEQUENCE,
        "mix_policy": policy.model_dump(),
        "customer_fundamentals": (
            f"{market} 家长买的是可信任的儿童智能陪伴，不是更便宜的喇叭。"
            "客户基本面决定货盘：陪伴魂+认证走独占/优质，套壳语音机压缩同质。"
        ),
        "ops_actions": actions,
        "decision": decision,
        "zone": zone,
    }


def company_playbook() -> dict:
    return {
        "business": "跨境 AI 玩具电商（中国供给 → 美英欧新站点）",
        "customer_fundamentals": "决策者是家长；信任=认证+陪伴体验；发现场在短视频，比价场在 Amazon。",
        "three_zones": {
            "EXCLUSIVE": "目的地市场授权/IP + 陪伴魂 + 认证齐。保护价盘，内容预算最高。",
            "ADVANTAGE": "无绝对授权，但成本/供货/TikTok内容/履约组合可验证。小预算测完再放。",
            "HOMOGENEOUS": "套壳语音机。只做内容效率套利，不做 Amazon 价格战，达不到退出线即换局。",
        },
        "entry_sequence": ENTRY_SEQUENCE,
        "channel_mix": {name: policy.model_dump() for name, policy in CHANNEL_MIX_POLICY.items()},
        "markets": MARKET_LABELS,
        "advantage_check": [
            "伪优势：Listing 写 AI Companion，没有人设记忆魂，也没有排他授权",
            "自嗨：团队觉得内容很燃，美国搜索/社交需求分低",
            "创造优势：目的地授权、认证、供货天数、TikTok 转化、家长信任体验",
        ],
        "weekly_cadence": [
            "辨货：魂/授权/认证/渠道，三区归位",
            "看盘：公司 20/30/50 + 分渠道配比",
            "定矛盾：价格战 / 伪 AI / 认证缺口 / 同质拖垮毛利",
            "出牌：TikTok TEST → Shopify → Amazon SCALE",
            "靠谱：退货、合规、时效；考核贡献利润不是 GMV",
        ],
    }
