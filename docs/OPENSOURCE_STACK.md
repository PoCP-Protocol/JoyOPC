# Open-source stack introduced into JoyOPC

JoyOPC 不 fork 开源商城。本仓库只 **compose**：

```text
CEO Cockpit / AI Workforce     自研
        │
JoyOPC Commerce Runtime        自研
        │
Content Factory + AI Provider  自研封装，参考 Listing Studio
        │
Channel Gateway                自研接口 + 官方 SDK
        │
Saleor + saleor-mcp            官方发行版
Amazon / TikTok / Shopify      外部渠道
```

## 引进清单

| 用途 | 引进方式 | 仓库 / 包 |
|---|---|---|
| Commerce Kernel | `vendor/saleor-platform` | [saleor/saleor-platform](https://github.com/saleor/saleor-platform) |
| AI 只读 Saleor | `vendor/saleor-mcp` + Adapter | [saleor/saleor-mcp](https://github.com/saleor/saleor-mcp) |
| Listing 字段映射参考 | `vendor/open-listing-studio` | [clawnify/open-listing-studio](https://github.com/clawnify/open-listing-studio) |
| 多渠道端口参考 | `vendor/openlinker` | [openlinker-project/openlinker](https://github.com/openlinker-project/openlinker) |
| Amazon Adapter | pip | [python-amazon-sp-api](https://github.com/saleweaver/python-amazon-sp-api) |
| Shopify Adapter | pip | [Shopify/shopify_python_api](https://github.com/Shopify/shopify_python_api) |
| TikTok Shop Adapter | 自研 httpx | 无对等高质量 Python SDK |
| 文本 AI Gateway | OpenAI-compatible HTTP | 与 V0.3 多模态 Provider 共用密钥 |

```powershell
powershell -File scripts/bootstrap_opensource.ps1
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

未配置渠道/模型密钥时：Channel Gateway 与 Content Factory 走 `DRY_RUN` / `local-template`，编排链仍可打通。
