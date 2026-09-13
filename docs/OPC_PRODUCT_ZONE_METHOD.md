# JoyOPC 产品三区选品方法论 v1

## 1. 独占区

**定义**：JoyOPC 对商品、销售权、IP、渠道、区域或关键供给资源具有可验证的排他控制权。

### 核心指标
- 独家/排他授权
- 产品独特性
- 渠道控制力
- 竞争可替代性
- 毛利空间
- 合规与供应风险

### 经营动作
- 优先资源投入
- 保护价格体系与渠道边界
- 建立独家期限/区域/平台/最低供货等合同字段
- 内容与广告优先级最高
- 争取长期用户与品牌资产

## 2. 优势区

**定义**：不存在绝对排他权，但 JoyOPC 在成本、供应、内容、品牌、履约、市场理解中的若干项形成组合优势。

### 核心指标
- 成本优势
- 供应稳定性与响应速度
- 内容生产/投放优势
- 品牌/用户资产
- 市场需求

### 经营动作
- 小预算测试
- 达到贡献利润/转化阈值后迅速放量
- 持续检测优势衰减
- 努力把优势区升级为独占区（例如获得平台/区域独家权）

## 3. 同质区

**定义**：商品容易被替代，价格透明，供应商和竞争者众多，JoyOPC 暂无明显控制权和组合优势。

### 核心原则
同质区不是完全不做，而是**只做效率套利**：
- 极强成本优势
- 极高内容转化效率
- 极快周转
- 极低获客成本
- 特定渠道红利

如果这些效率条件不成立，JoyOPC 应快速淘汰，而不是为了 GMV 陷入价格战。

## 4. 系统化

JoyOPC V0.1 已将方法论实现为 `ProductZoneEngine`，输入：
- exclusive_rights
- uniqueness
- channel_control
- cost_advantage
- supply_advantage
- content_advantage
- brand_advantage
- market_demand
- competition_intensity
- expected_margin_pct
- compliance_risk
- return_risk
- cash_cycle_days

输出：
- zone
- opportunity_score
- decision
- reasons
- recommended_actions

所有阈值通过 `SelectionPolicy` 配置，后续可按国家、渠道、品类、OPC公司建立策略版本。
