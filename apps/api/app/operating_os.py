from __future__ import annotations

from dataclasses import dataclass

from .crossborder_ai_toy import CHANNEL_MIX_POLICY, classify_crossborder_advantage, company_playbook
from .schemas import MixPolicy, SelectionInput, SkuPhilosophy, StrategyCircle


ADVANTAGE_SOURCE_LABELS = {
    "CONTROL_RIGHTS": "控制权创造优势",
    "COGNITION": "改变认知创造优势",
    "MODEL": "改变模式创造优势",
    "COST": "投资/成本创造优势",
    "SUPPLY": "保供创造优势",
    "EXPERIENCE": "超级体验创造优势",
}

CONTRADICTION_LABELS = {
    "PRICE_WAR": "同质区价格战：需求在、控制权不在、利润被竞争抽干",
    "FAKE_ADVANTAGE": "伪优势： uniqueness/品牌自评高，但无可验证控制权且竞争已内卷",
    "SELF_INTOXICATION": "自嗨型优势：内容/品牌自我感觉良好，市场基本面并未买单",
    "ADVANTAGE_EROSION": "优势可复制：优质区组合优势正在被竞争侵蚀",
    "CONTROL_VS_RISK": "控制权与风险对冲：独占资产存在，但合规/退货/周转风险过高",
    "MIX_DRAG": "三区图失衡：同质区占比过高，组合利润率被拖垮",
    "EXCLUSIVE_SHORTAGE": "独占资产不足：货盘缺少可保护的利润锚",
    "EXECUTION_GAP": "谋略未落地：机会可见，但决策仍停在 HOLD / 未测试",
    "RELIABILITY_GAP": "靠谱缺口：交付/质量/售后无法支撑“成为靠谱的人”",
    "OPTIMIZE_MIX": "前端铁三角：优化三区图、抓住主要矛盾、把谋略落到资源分配",
}

GAMING_MOVES = {
    "HOLD_CARDS": "抓牌：先锁授权、供给与内容资产，不急于放量",
    "PLAY_CARDS": "出牌：小预算验证后把预算打到优势最强的1-2个点",
    "CHANGE_BOARD": "换局：淘汰无效率同质品，把货盘配比推向目标三区图",
}


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def classify_advantage(x: SelectionInput) -> tuple[str, list[str], list[str]]:
    """把“优势”拆成真伪，避免把自评当护城河。"""
    sources: list[str] = []
    if x.exclusive_rights:
        sources.append("CONTROL_RIGHTS")
    if x.uniqueness >= 70 and x.content_advantage >= 65:
        sources.append("COGNITION")
    if x.channel_control >= 70:
        sources.append("MODEL")
    if x.cost_advantage >= 75:
        sources.append("COST")
    if x.supply_advantage >= 75:
        sources.append("SUPPLY")
    if x.brand_advantage >= 70 and x.return_risk <= 35 and x.uniqueness >= 60:
        sources.append("EXPERIENCE")

    claimed_moat = max(x.uniqueness, x.brand_advantage)
    fake = (
        claimed_moat >= 70
        and not x.exclusive_rights
        and x.competition_intensity >= 70
        and x.channel_control < 55
        and x.cost_advantage < 70
    )
    self_intoxicated = (x.content_advantage >= 75 or x.brand_advantage >= 75) and x.market_demand < 52

    reasons: list[str] = []
    cb_fake = classify_crossborder_advantage(x)
    if cb_fake:
        quality = "FAKE"
        reasons.append("跨境 AI 玩具伪优势：商品叙事是 AI，但没有陪伴魂也没有排他授权。")
        return quality, sources, reasons
    if fake:
        quality = "FAKE"
        reasons.append("自评独特性/品牌偏高，但缺少排他权、渠道控制与成本壁垒，属于伪优势。")
    elif self_intoxicated:
        quality = "SELF_INTOXICATED"
        reasons.append("内容或品牌评分高，但市场需求基本面弱，属于自嗨型优势。")
    elif sources:
        quality = "CREATED"
        reasons.append("优势来自可验证的创造动作：" + "、".join(ADVANTAGE_SOURCE_LABELS[s] for s in sources) + "。")
    else:
        quality = "WEAK"
        reasons.append("尚未形成可保护的创造优势；若不能把成本/供应/内容做成可验证动作，将退回同质区。")
    return quality, sources, reasons


def reliability_score(x: SelectionInput) -> float:
    """客户篇：成为靠谱的人。四管理 = 承诺 / 交付 / 质量 / 合规。"""
    promise = _clamp((x.uniqueness + x.content_advantage) / 2)
    delivery = _clamp(x.supply_advantage)
    quality = _clamp(100.0 - x.return_risk)
    compliance = _clamp(100.0 - x.compliance_risk)
    return round((promise * 0.20 + delivery * 0.30 + quality * 0.30 + compliance * 0.20), 1)


def sku_contradiction(x: SelectionInput, zone: str, decision: str, quality: str, risk_score: float) -> str:
    if quality == "FAKE":
        return "FAKE_ADVANTAGE"
    if quality == "SELF_INTOXICATED":
        return "SELF_INTOXICATION"
    if zone == "HOMOGENEOUS" and x.competition_intensity >= 70 and x.expected_margin_pct < 30:
        return "PRICE_WAR"
    if zone == "EXCLUSIVE" and risk_score > 60:
        return "CONTROL_VS_RISK"
    if zone == "ADVANTAGE" and x.competition_intensity >= 72:
        return "ADVANTAGE_EROSION"
    if reliability_score(x) < 48:
        return "RELIABILITY_GAP"
    if decision == "HOLD" and x.market_demand >= 70:
        return "EXECUTION_GAP"
    return "OPTIMIZE_MIX"


def gaming_move(contradiction: str, decision: str) -> str:
    if contradiction in {"FAKE_ADVANTAGE", "SELF_INTOXICATION", "PRICE_WAR", "MIX_DRAG"}:
        return "CHANGE_BOARD"
    if decision in {"SCALE", "TEST"}:
        return "PLAY_CARDS"
    return "HOLD_CARDS"


def diagnose_sku(
    x: SelectionInput,
    *,
    zone: str,
    decision: str,
    risk_score: float,
) -> SkuPhilosophy:
    quality, sources, quality_reasons = classify_advantage(x)
    quality_labels = {
        "FAKE": "伪优势",
        "SELF_INTOXICATED": "自嗨型优势",
        "CREATED": "创造优势",
        "WEAK": "优势未立",
    }
    contradiction = sku_contradiction(x, zone, decision, quality, risk_score)
    move = gaming_move(contradiction, decision)
    reliable = reliability_score(x)

    strategy = {
        "PRICE_WAR": "只做效率套利：设利润/周转/内容转化退出线，达不到就换局。",
        "FAKE_ADVANTAGE": "停止按独占投入；先补排他合同、渠道边界或真实成本壁垒。",
        "SELF_INTOXICATION": "用市场基本面校准内容叙事，禁止用自评内容分放量。",
        "ADVANTAGE_EROSION": "把1-2个最强优势做成短期不可复制动作，并争取升格独占。",
        "CONTROL_VS_RISK": "先处理合规、退货、资金周转，再保护价格体系。",
        "RELIABILITY_GAP": "四管理补课：交付、质量、售后先于投放。",
        "EXECUTION_GAP": "把谋略拆成测试预算、渠道、内容与退出线，进入谋略落地。",
        "OPTIMIZE_MIX": "按三区图分配资源：独占保护、优质验证、同质限流。",
        "MIX_DRAG": "压缩同质区SKU，把资源转到独占/优质区。",
        "EXCLUSIVE_SHORTAGE": "优先谈独家、IP、区域或供给控制权。",
    }[contradiction]

    implementation = {
        "EXCLUSIVE": "锁定授权范围与期限，价格保护，内容预算最高优先级。",
        "ADVANTAGE": "小预算测转化，过阈值放量，每周检测优势是否被复制。",
        "HOMOGENEOUS": "限制测试预算与库存，达不到效率条件立即淘汰。",
    }[zone]

    return SkuPhilosophy(
        advantage_quality=quality,
        advantage_quality_label=quality_labels[quality],
        advantage_sources=sources,
        advantage_source_labels=[ADVANTAGE_SOURCE_LABELS[s] for s in sources],
        main_contradiction_code=contradiction,
        main_contradiction=CONTRADICTION_LABELS[contradiction],
        reliability_score=reliable,
        strategy=strategy,
        implementation=implementation,
        gaming_move=move,
        gaming_move_label=GAMING_MOVES[move],
        notes=quality_reasons,
    )


PROCESS_LOOP = [
    {"code": "ADVANTAGE_BUILD", "no": "0", "label": "持续建立优势", "talent": "A", "owner": "Buyer AI"},
    {"code": "OPTIMIZE_MIX", "no": "①", "label": "优化三区图", "talent": "V", "owner": "Commerce CFO"},
    {"code": "CONTRADICTION", "no": "②", "label": "抓住主要矛盾", "talent": "E", "owner": "Market AI"},
    {"code": "STRATEGY", "no": "③", "label": "谋略", "talent": "A", "owner": "Buyer AI"},
    {"code": "IMPLEMENT", "no": "④", "label": "谋略落地", "talent": "L", "owner": "Merchandiser AI"},
    {"code": "GAMING", "no": "⑤", "label": "博弈", "talent": "E", "owner": "Pricing AI"},
    {"code": "CUSTOMER", "no": "⑥", "label": "成为靠谱的人", "talent": "U", "owner": "Product Intelligence AI"},
    {"code": "GAMING_CHAPTER", "no": "⑦", "label": "博弈篇：抓牌-出牌-换局", "talent": "E", "owner": "Pricing AI"},
    {"code": "GOALS", "no": "⑧", "label": "目标与考核", "talent": "V", "owner": "Commerce CFO"},
    {"code": "TALENT", "no": "⑨", "label": "人才 VALUE", "talent": "A", "owner": "Buyer AI"},
    {"code": "RUN", "no": "⑩", "label": "奔跑创业路上", "talent": "L", "owner": "Merchandiser AI"},
]

TALENT_VALUE = {
    "V": {"letter": "V", "name": "价值", "meaning": "考核组合利润与三区配比，禁止用 GMV 替代经营质量。"},
    "A": {"letter": "A", "name": "优势", "meaning": "只把可验证的创造优势当投入依据，识别伪优势与自嗨。"},
    "L": {"letter": "L", "name": "落地", "meaning": "谋略必须拆成渠道、预算、退出线与授权动作。"},
    "U": {"letter": "U", "name": "靠谱", "meaning": "承诺、交付、质量、合规四管理，先于投放。"},
    "E": {"letter": "E", "name": "进化", "meaning": "危机时优势转换；僵局时换局，而不是加预算。"},
}

AGENT_TALENT = {
    "Buyer AI": "A",
    "Pricing AI": "V",
    "Merchandiser AI": "L",
    "Content AI": "A",
    "Market AI": "E",
    "Commerce CFO": "V",
    "Product Intelligence AI": "U",
}

CONTRADICTION_TO_STEP = {
    "MIX_DRAG": "OPTIMIZE_MIX",
    "EXCLUSIVE_SHORTAGE": "OPTIMIZE_MIX",
    "FAKE_ADVANTAGE": "ADVANTAGE_BUILD",
    "SELF_INTOXICATION": "ADVANTAGE_BUILD",
    "PRICE_WAR": "CONTRADICTION",
    "ADVANTAGE_EROSION": "CONTRADICTION",
    "CONTROL_VS_RISK": "STRATEGY",
    "EXECUTION_GAP": "IMPLEMENT",
    "RELIABILITY_GAP": "CUSTOMER",
    "OPTIMIZE_MIX": "GOALS",
}


def talent_for_agent(agent: str) -> dict:
    letter = AGENT_TALENT.get(agent, "L")
    meta = TALENT_VALUE[letter]
    return {"talent": letter, "talent_label": f"{letter} {meta['name']}", "talent_meaning": meta["meaning"]}


def implementation_play(zone: str, philosophy: SkuPhilosophy) -> dict:
    """把单品结论翻译成管理过程中的下一步任务。"""
    step = CONTRADICTION_TO_STEP.get(philosophy.main_contradiction_code, "IMPLEMENT")
    owner = next((p["owner"] for p in PROCESS_LOOP if p["code"] == step), "Merchandiser AI")
    talent = talent_for_agent(owner)
    return {
        "process_step": step,
        "owner": owner,
        "gaming_move": philosophy.gaming_move,
        "title": f"{philosophy.gaming_move_label} · {philosophy.advantage_quality_label}",
        "recommendation": (
            f"[{step} · {talent['talent_label']}] {philosophy.strategy} "
            f"落地：{philosophy.implementation}"
        ),
        **talent,
    }


def approve_management_gate(
    *,
    zone: str,
    decision: str,
    quality: str,
    homogeneous_share: float,
    homogeneous_alert: float,
) -> dict:
    """CEO 批准候选商品时的经营过程闸门。"""
    blocked = False
    force_decision = decision
    reasons: list[str] = []
    if quality in {"FAKE", "SELF_INTOXICATED"} and decision == "SCALE":
        force_decision = "TEST"
        reasons.append("伪优势/自嗨不得 SCALE，降为 TEST，禁止按独占配置预算。")
    if zone == "HOMOGENEOUS" and homogeneous_share >= homogeneous_alert:
        if decision == "SCALE":
            blocked = True
            reasons.append("同质区占比已超警戒，换局优先于放量，CEO 批准 SCALE 被经营OS拒绝。")
        elif decision == "TEST":
            force_decision = "HOLD"
            reasons.append("同质区占比过高，TEST 降为 HOLD，先优化三区图再测。")
    return {
        "blocked": blocked,
        "force_decision": force_decision,
        "reasons": reasons,
        "process_step": "GAMING" if blocked or force_decision != decision else "IMPLEMENT",
    }


def publish_management_error(
    *,
    zone: str,
    decision: str,
    homogeneous_share: float,
    homogeneous_alert: float,
) -> str | None:
    if decision in {"HOLD", "REJECT"}:
        return f"三区决策为 {decision}，不允许直接发布"
    if zone == "HOMOGENEOUS" and homogeneous_share >= homogeneous_alert:
        return "经营OS换局：同质区占比过高，不允许再向真实渠道放量。先淘汰无效率 SKU。"
    return None


def build_management_process(
    *,
    phase: str,
    contradiction: str,
    mix_share: dict[str, float],
    target: dict[str, float],
    blended_margin: float,
    target_margin: float,
    fake_count: int,
    weak_reliability: int,
    actions: list[str],
    circles: list[StrategyCircle],
    policy: MixPolicy,
) -> dict:
    """把墙上的 ①–⑩ 变成 JoyOPC 每周经营节奏、考核与人才分工。"""
    active_code = CONTRADICTION_TO_STEP.get(contradiction, "OPTIMIZE_MIX")
    if phase.startswith("奔跑") and contradiction == "OPTIMIZE_MIX":
        active_code = "RUN"
    loop = []
    for step in PROCESS_LOOP:
        loop.append({**step, "active": step["code"] == active_code, **TALENT_VALUE[step["talent"]]})

    def kpi(name: str, current: float, target_value: float, unit: str = "pt", invert: bool = False) -> dict:
        gap = round(current - target_value, 1)
        if invert:
            healthy = current <= target_value
        elif "独占" in name or "优质" in name:
            healthy = current >= target_value - 5
        else:
            healthy = current >= target_value
        return {
            "name": name,
            "current": current,
            "target": target_value,
            "unit": unit,
            "gap": gap,
            "status": "HEALTHY" if healthy else "ALERT",
        }

    goals = [
        kpi("独占区SKU占比", mix_share.get("EXCLUSIVE", 0), target["EXCLUSIVE"], "%"),
        kpi("优质区SKU占比", mix_share.get("ADVANTAGE", 0), target["ADVANTAGE"], "%"),
        kpi("同质区SKU占比", mix_share.get("HOMOGENEOUS", 0), target["HOMOGENEOUS"], "%", invert=True),
        kpi("组合毛利", blended_margin, target_margin, "%"),
        kpi("伪优势/自嗨件数", float(fake_count), 0, "个", invert=True),
        kpi("靠谱缺口件数", float(weak_reliability), 0, "个", invert=True),
    ]
    alert_goals = [g for g in goals if g["status"] == "ALERT"]
    ceo_agenda = [
        f"本周阶段：{phase}",
        f"主要矛盾：{CONTRADICTION_LABELS[contradiction]}",
        f"当前过程：{[s for s in PROCESS_LOOP if s['code']==active_code][0]['no']} {[s for s in PROCESS_LOOP if s['code']==active_code][0]['label']}",
    ]
    ceo_agenda.extend(actions[:3])
    if alert_goals:
        ceo_agenda.append("考核红灯：" + "；".join(f"{g['name']} {g['current']}{g['unit']}" for g in alert_goals))
    alert_circles = [c.label for c in circles if c.status == "ALERT"]
    if alert_circles:
        ceo_agenda.append("谋略圈告警：" + "、".join(alert_circles) + " → 先优势转换，不加投放。")

    return {
        "cadence": "周经营节奏：辨优势真伪 → 看三区图 → 定主要矛盾 → 谋略六圈 → 落地/博弈 → 靠谱四管理 → 考核 VALUE",
        "active_step": active_code,
        "process_loop": loop,
        "goals": goals,
        "talent_value": [{"letter": k, **v, "agents": [a for a, letter in AGENT_TALENT.items() if letter == k]} for k, v in TALENT_VALUE.items()],
        "ceo_agenda": ceo_agenda,
        "policy": {
            "homogeneous_alert_pct": policy.homogeneous_alert_pct,
            "target_share": target,
        },
    }


@dataclass(slots=True)
class MixItem:
    name: str
    zone: str
    expected_margin_pct: float
    gmv: float = 0.0
    contribution_profit: float = 0.0
    decision: str = "HOLD"
    status: str = "ACTIVE"
    uniqueness: float = 50
    channel_control: float = 50
    cost_advantage: float = 50
    supply_advantage: float = 50
    content_advantage: float = 50
    brand_advantage: float = 50
    market_demand: float = 50
    competition_intensity: float = 50
    compliance_risk: float = 30
    return_risk: float = 30
    cash_cycle_days: int = 30
    exclusive_rights: bool = False
    risk_score: float = 40
    opportunity_score: float = 50
    market: str = "US"
    channel: str = "TikTok Shop"


def _share(counts: dict[str, float]) -> dict[str, float]:
    total = sum(counts.values()) or 1.0
    return {k: round(v / total * 100.0, 1) for k, v in counts.items()}


def _avg(items: list[MixItem], getter) -> float:
    if not items:
        return 0.0
    return round(sum(getter(i) for i in items) / len(items), 1)


def _circle(code: str, label: str, score: float, note: str) -> StrategyCircle:
    status = "HEALTHY" if score >= 68 else "WATCH" if score >= 50 else "ALERT"
    return StrategyCircle(code=code, label=label, score=round(_clamp(score), 1), status=status, note=note)


def analyze_portfolio(items: list[MixItem], policy: MixPolicy | None = None) -> dict:
    """第二张图：客户基本面 → 产品三区分布 → 用策略把配比推向更高利润。"""
    policy = policy or MixPolicy()
    live = [i for i in items if i.status not in {"REJECTED"}]
    zones = ("EXCLUSIVE", "ADVANTAGE", "HOMOGENEOUS")
    sku_counts = {z: float(sum(1 for i in live if i.zone == z)) for z in zones}
    sku_share = _share(sku_counts)
    gmv_counts = {z: sum(i.gmv for i in live if i.zone == z) for z in zones}
    gmv_share = _share(gmv_counts) if sum(gmv_counts.values()) else sku_share
    margin_by_zone = {
        z: _avg([i for i in live if i.zone == z], lambda i: i.expected_margin_pct) for z in zones
    }
    blended_margin = round(
        sum(sku_share[z] / 100.0 * (margin_by_zone[z] or 0) for z in zones),
        1,
    )
    target_margin = round(
        policy.exclusive_target_pct / 100.0 * (margin_by_zone["EXCLUSIVE"] or 45)
        + policy.advantage_target_pct / 100.0 * (margin_by_zone["ADVANTAGE"] or 32)
        + policy.homogeneous_target_pct / 100.0 * (margin_by_zone["HOMOGENEOUS"] or 18),
        1,
    )

    target = {
        "EXCLUSIVE": policy.exclusive_target_pct,
        "ADVANTAGE": policy.advantage_target_pct,
        "HOMOGENEOUS": policy.homogeneous_target_pct,
    }
    gaps = {z: round(sku_share[z] - target[z], 1) for z in zones}

    fake_count = 0
    weak_reliability = 0
    for i in live:
        payload = SelectionInput(
            product_name=i.name,
            exclusive_rights=i.exclusive_rights,
            uniqueness=i.uniqueness,
            channel_control=i.channel_control,
            cost_advantage=i.cost_advantage,
            supply_advantage=i.supply_advantage,
            content_advantage=i.content_advantage,
            brand_advantage=i.brand_advantage,
            market_demand=i.market_demand,
            competition_intensity=i.competition_intensity,
            expected_margin_pct=i.expected_margin_pct,
            compliance_risk=i.compliance_risk,
            return_risk=i.return_risk,
            cash_cycle_days=i.cash_cycle_days,
        )
        quality, _, _ = classify_advantage(payload)
        if quality in {"FAKE", "SELF_INTOXICATED"}:
            fake_count += 1
        if reliability_score(payload) < 48:
            weak_reliability += 1

    if sku_share["HOMOGENEOUS"] >= policy.homogeneous_alert_pct:
        contradiction = "MIX_DRAG"
    elif sku_share["EXCLUSIVE"] < 10 and len(live) >= 3:
        contradiction = "EXCLUSIVE_SHORTAGE"
    elif fake_count:
        contradiction = "FAKE_ADVANTAGE"
    elif weak_reliability:
        contradiction = "RELIABILITY_GAP"
    else:
        contradiction = "OPTIMIZE_MIX"

    actions: list[str] = []
    if gaps["HOMOGENEOUS"] > 0:
        actions.append(f"同质区高出目标 {gaps['HOMOGENEOUS']}pt，淘汰无效率套利的 SKU。")
    if gaps["EXCLUSIVE"] < 0:
        actions.append(f"独占区低于目标 {abs(gaps['EXCLUSIVE'])}pt，优先锁授权/IP/区域控制权。")
    if gaps["ADVANTAGE"] < 0:
        actions.append(f"优质区低于目标 {abs(gaps['ADVANTAGE'])}pt，把可验证成本/供应/内容优势做成测试放量。")
    if blended_margin < target_margin:
        actions.append(f"组合毛利 {blended_margin}% 低于目标配比推演 {target_margin}%，用三区图而不是 GMV 调仓。")
    if not actions:
        actions.append("配比接近目标三区图，进入谋略落地与博弈：保护独占、验证优质、限制同质。")

    circles = [
        _circle(
            "CRISIS",
            "危机预警圈",
            100.0 - _avg(live, lambda i: i.risk_score or (i.compliance_risk * 0.5 + i.return_risk * 0.5)),
            "风险抬头时先做优势转换，而不是加投放。",
        ),
        _circle("SUPPLY", "保供圈", _avg(live, lambda i: i.supply_advantage), "供给稳定是优质区放量的前提。"),
        _circle(
            "PROFIT_WALK",
            "利润步行圈",
            _clamp(50 + (blended_margin - 22) * 1.6),
            "每一步资源分配都要能看见组合利润率在走，而不是只看见 GMV。",
        ),
        _circle(
            "COGNITION",
            "认知拉齐圈",
            _avg(live, lambda i: min(i.content_advantage, i.uniqueness + 10)),
            "内容叙事必须与产品真实差异对齐，防止自嗨。",
        ),
        _circle("QUALITY", "质量圈", 100.0 - _avg(live, lambda i: i.return_risk), "退货与体验决定能不能成为靠谱的人。"),
        _circle("ECOSYSTEM", "生态圈", _avg(live, lambda i: (i.channel_control + (80 if i.exclusive_rights else 40)) / 2), "渠道、授权与供给伙伴构成可保护的生态。"),
    ]
    alert_circles = [c.label for c in circles if c.status == "ALERT"]
    phase = "危机管理 / 优势转换" if alert_circles or contradiction in {"FAKE_ADVANTAGE", "MIX_DRAG", "PRICE_WAR"} else (
        "奔跑创业路上" if contradiction == "OPTIMIZE_MIX" and sku_share["HOMOGENEOUS"] <= target["HOMOGENEOUS"] + 5 else "追求卓越：前端铁三角"
    )

    return {
        "phase": phase,
        "iron_triangle": ["优化三区图", "抓住主要矛盾", "谋略 → 落地 → 博弈"],
        "main_contradiction_code": contradiction,
        "main_contradiction": CONTRADICTION_LABELS[contradiction],
        "customer_fundamentals": "跨境 AI 玩具：家长买信任的陪伴，不是更便宜的喇叭。用客户基本面决定三区货盘，再按渠道出牌。",
        "mix": {
            "sku_share": sku_share,
            "gmv_share": gmv_share,
            "avg_margin_by_zone": margin_by_zone,
            "current_blended_margin_pct": blended_margin,
            "target_blended_margin_pct": target_margin,
            "target_share": target,
            "gaps_pt": gaps,
            "sku_counts": {z: int(sku_counts[z]) for z in zones},
        },
        "advantage_audit": {
            "fake_or_intoxicated": fake_count,
            "reliability_gaps": weak_reliability,
            "live_skus": len(live),
        },
        "strategy_circles": [c.model_dump() for c in circles],
        "recommended_actions": actions,
        "gaming_move": GAMING_MOVES[gaming_move(contradiction, "HOLD")],
        "targets_note": "默认目标配比来自经营哲学图：独占 20% / 优质 30% / 同质 50%；危机盘可先从 10/20/70 往上迁。",
        "management": build_management_process(
            phase=phase,
            contradiction=contradiction,
            mix_share=sku_share,
            target=target,
            blended_margin=blended_margin,
            target_margin=target_margin,
            fake_count=fake_count,
            weak_reliability=weak_reliability,
            actions=actions,
            circles=circles,
            policy=policy,
        ),
        "crossborder": {
            **company_playbook(),
            "channel_mix_snapshot": _channel_mix_snapshot(live),
        },
    }


def _channel_mix_snapshot(live: list[MixItem]) -> list[dict]:
    grouped: dict[str, list[MixItem]] = {}
    for item in live:
        grouped.setdefault(item.channel or "MULTI", []).append(item)
    snapshot = []
    for channel, rows in grouped.items():
        policy = CHANNEL_MIX_POLICY.get(channel, MixPolicy())
        counts = {z: float(sum(1 for r in rows if r.zone == z)) for z in ("EXCLUSIVE", "ADVANTAGE", "HOMOGENEOUS")}
        snapshot.append(
            {
                "channel": channel,
                "sku_count": len(rows),
                "sku_share": _share(counts),
                "target_share": {
                    "EXCLUSIVE": policy.exclusive_target_pct,
                    "ADVANTAGE": policy.advantage_target_pct,
                    "HOMOGENEOUS": policy.homogeneous_target_pct,
                },
                "homogeneous_alert_pct": policy.homogeneous_alert_pct,
            }
        )
    return snapshot
