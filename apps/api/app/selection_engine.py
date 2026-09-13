from __future__ import annotations

from dataclasses import dataclass

from .schemas import SelectionInput, SelectionPolicy, SelectionResult


ZONE_LABELS = {
    "EXCLUSIVE": "独占区",
    "ADVANTAGE": "优势区",
    "HOMOGENEOUS": "同质区",
}


@dataclass(slots=True)
class ProductZoneEngine:
    """JoyOPC 产品三区选品引擎。

    规则原则：
    - 独占区：优先保护和放大“控制权”，而不是单纯追热点。
    - 优势区：要求成本/供应/内容/品牌等形成可持续组合优势。
    - 同质区：默认谨慎，只有利润与执行效率显著成立时才允许规模化。
    """

    policy: SelectionPolicy

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(100.0, value))

    @staticmethod
    def _margin_score(margin_pct: float) -> float:
        # 0% => 0, 20% => 33, 40% => 66, 60%+ => 100
        return max(0.0, min(100.0, margin_pct / 60.0 * 100.0))

    @staticmethod
    def _cash_cycle_score(days: int) -> float:
        # 0 天最好；90 天及以上记为 0 分。
        return max(0.0, min(100.0, 100.0 - days / 90.0 * 100.0))

    def evaluate(self, x: SelectionInput) -> SelectionResult:
        exclusivity = 100.0 if x.exclusive_rights else 0.0
        competition_inverse = 100.0 - x.competition_intensity

        exclusive_score = self._clamp(
            exclusivity * 0.40
            + x.uniqueness * 0.25
            + x.channel_control * 0.20
            + competition_inverse * 0.15
        )

        advantage_score = self._clamp(
            x.cost_advantage * 0.25
            + x.supply_advantage * 0.20
            + x.content_advantage * 0.20
            + x.brand_advantage * 0.10
            + x.market_demand * 0.25
        )

        risk_score = self._clamp(
            x.compliance_risk * 0.45
            + x.return_risk * 0.35
            + (100.0 - self._cash_cycle_score(x.cash_cycle_days)) * 0.20
        )

        if x.exclusive_rights and exclusive_score >= self.policy.exclusive_zone_threshold:
            zone = "EXCLUSIVE"
        elif advantage_score >= self.policy.advantage_zone_threshold:
            zone = "ADVANTAGE"
        else:
            zone = "HOMOGENEOUS"

        margin_score = self._margin_score(x.expected_margin_pct)
        base_score = self._clamp(
            x.market_demand * 0.24
            + competition_inverse * 0.12
            + margin_score * 0.22
            + x.cost_advantage * 0.10
            + x.supply_advantage * 0.08
            + x.content_advantage * 0.10
            + x.uniqueness * 0.08
            + (100.0 - risk_score) * 0.06
        )

        zone_adjustment = {"EXCLUSIVE": 10.0, "ADVANTAGE": 5.0, "HOMOGENEOUS": -8.0}[zone]
        opportunity_score = self._clamp(base_score + zone_adjustment)

        strong_advantages = sum(
            score >= 75
            for score in [
                x.cost_advantage,
                x.supply_advantage,
                x.content_advantage,
                x.brand_advantage,
                x.uniqueness,
            ]
        )

        if risk_score > 75 or x.expected_margin_pct < 12:
            decision = "REJECT"
        elif zone == "EXCLUSIVE":
            if (
                opportunity_score >= self.policy.scale_score_exclusive
                and x.expected_margin_pct >= self.policy.min_margin_exclusive
                and risk_score <= self.policy.max_risk_for_scale
            ):
                decision = "SCALE"
            elif opportunity_score >= 52:
                decision = "TEST"
            else:
                decision = "HOLD"
        elif zone == "ADVANTAGE":
            if (
                opportunity_score >= self.policy.scale_score_advantage
                and x.expected_margin_pct >= self.policy.min_margin_advantage
                and risk_score <= self.policy.max_risk_for_scale
            ):
                decision = "SCALE"
            elif opportunity_score >= 56:
                decision = "TEST"
            else:
                decision = "HOLD"
        else:
            # 同质区必须用更严格的门槛，避免“看起来有需求”但陷入价格战。
            if (
                opportunity_score >= self.policy.scale_score_homogeneous
                and x.expected_margin_pct >= self.policy.min_margin_homogeneous
                and strong_advantages >= self.policy.homogeneous_min_strong_advantages
                and risk_score <= self.policy.max_risk_for_scale
            ):
                decision = "SCALE"
            elif (
                opportunity_score >= 62
                and x.expected_margin_pct >= 25
                and strong_advantages >= 1
                and risk_score <= 65
            ):
                decision = "TEST"
            elif opportunity_score >= 52:
                decision = "HOLD"
            else:
                decision = "REJECT"

        reasons: list[str] = []
        actions: list[str] = []

        if zone == "EXCLUSIVE":
            reasons.append("存在可验证的独家/控制权，优先进入独占区经营。")
            actions.extend(["锁定授权范围与期限", "建立渠道价格保护", "优先配置内容与广告预算"])
        elif zone == "ADVANTAGE":
            reasons.append("未形成绝对独占，但综合经营优势达到优势区门槛。")
            actions.extend(["明确最强的1-2个优势来源", "小预算验证转化后放量", "持续监控优势是否被复制"])
        else:
            reasons.append("当前缺乏足够独占权或组合优势，按同质区严格经营。")
            actions.extend(["限制首轮测试预算", "用利润/周转/内容效率设退出线", "不能形成优势则快速淘汰"])

        if x.expected_margin_pct >= 40:
            reasons.append(f"预期毛利 {x.expected_margin_pct:.1f}% 较强。")
        elif x.expected_margin_pct < 25:
            reasons.append(f"预期毛利仅 {x.expected_margin_pct:.1f}%，利润安全垫偏薄。")

        if x.market_demand >= 75:
            reasons.append("市场需求评分高。")
        if x.competition_intensity >= 75:
            reasons.append("竞争强度高，需防止陷入价格战。")
        if risk_score > self.policy.max_risk_for_scale:
            reasons.append("综合风险高于规模化阈值。")
            actions.append("先处理合规、退货或资金周转风险，再扩大投放")

        actions.append(f"当前建议：{decision}")

        return SelectionResult(
            product_name=x.product_name,
            zone=zone,
            zone_label=ZONE_LABELS[zone],
            opportunity_score=round(opportunity_score, 1),
            decision=decision,
            exclusive_score=round(exclusive_score, 1),
            advantage_score=round(advantage_score, 1),
            risk_score=round(risk_score, 1),
            reasons=reasons,
            recommended_actions=actions,
        )
