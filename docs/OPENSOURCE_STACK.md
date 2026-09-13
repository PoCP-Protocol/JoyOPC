# Open-source stack introduced into JoyOPC

JoyOPC 不 fork 开源商城。本仓库只 **compose**：

```text
CEO Cockpit / AI Workforce     自研
        │
JoyOPC Commerce Runtime        自研
        │
Content Factory                自研；Amazon 上限参考 Listing Studio
SKU Matcher                    自研；绑定策略参考 TradeMind
Fulfillment sourcing           自研；策略名参考 KubeRiva OMS
Channel Gateway                自研接口 + 官方 SDK
        │
Saleor + saleor-mcp            官方发行版（可选内核）
Amazon / TikTok / Shopify      外部渠道
Shopee / Lazada                Marketeer 观察列表，尚未做 Adapter
```

## 引进清单

| 用途 | 引进方式 | 仓库 / 包 |
|---|---|---|
| Commerce Kernel | `vendor/saleor-platform` | [saleor/saleor-platform](https://github.com/saleor/saleor-platform) |
| AI 只读 Saleor | `vendor/saleor-mcp` | [saleor/saleor-mcp](https://github.com/saleor/saleor-mcp) |
| Listing 字段上限 | `vendor/open-listing-studio` → `listing_limits.py` | [clawnify/open-listing-studio](https://github.com/clawnify/open-listing-studio) |
| 多渠道端口工厂 | `vendor/openlinker` | [openlinker-project/openlinker](https://github.com/openlinker-project/openlinker) |
| 履约选点策略 | `vendor/kuberiva-oms` → `fulfillment_sourcing.py` | [KubeRiva/OMS](https://github.com/KubeRiva/OMS) Apache-2.0 |
| SEA 渠道观察 | `vendor/marketeer` | [codustry/marketeer](https://github.com/codustry/marketeer) Apache-2.0（仍处 design phase） |
| SKU 绑定 / 刊登草稿 | `vendor/trademind-ai` → `sku_matcher.py` | [lien0219/trademind-ai](https://github.com/lien0219/trademind-ai) Apache-2.0 |
| Amazon Adapter | pip `python-amazon-sp-api` | [saleweaver/python-amazon-sp-api](https://github.com/saleweaver/python-amazon-sp-api) MIT |
| Shopify Adapter | JoyOPC GraphQL httpx | 官方 Admin GraphQL；**不**用已弃用的 REST `shopify_python_api` |
| TikTok Shop Adapter | 自研 HMAC httpx | 无对等高质量 Python SDK；端口模型参考 Marketeer |

```powershell
powershell -File scripts/bootstrap_opensource.ps1
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

未配置渠道/模型密钥时：Channel Gateway 与 Content Factory 走 `DRY_RUN` / `local-template`，编排链仍可打通。

JoyOPC **不会**把 KubeRiva 或 TradeMind 当成操作系统跑起来；vendor 克隆只作端口与策略参考。

上架 P 图 / 短视频分镜见 `docs/MEDIA_STUDIO.md`。
