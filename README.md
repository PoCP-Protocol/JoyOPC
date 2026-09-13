# JoyOPC V0.4 — 真实渠道连接 + 商品发布 + 订单回流 + SKU级真实利润

JoyOPC 是面向 AI 玩具销售型 OPC 公司的 AI-native Commerce OS。V0.4 在 V0.3 的“真实货盘 + 多模态 + 真实市场信号 + 产品三区”之上，把选品推进到真实电商交易闭环。

## V0.4 核心闭环

```text
真实供应商/市场/多模态
        ↓
产品三区：独占区 / 优势区 / 同质区
        ↓
CEO Approval
        ↓
Master Product
        ↓
Channel Account
        ↓
商品发布
        ↓
Shopify / Amazon / TikTok Shop
        ↓
真实订单回流（幂等）
        ↓
Order + Order Item + SKU Mapping
        ↓
平台费 / 广告 / 物流 / 退款成本账本
        ↓
SKU Contribution Profit
        ↓
RECONCILED / PROVISIONAL
        ↓
AI经营决策
```

## 1. 真实渠道账号

新增 `ChannelAccount`。数据库只保存非秘密标识：

- 渠道 / 市场
- Shopify store domain
- Amazon seller ID / marketplace ID
- TikTok Shop cipher
- 环境变量前缀

**Access Token、Client Secret、Refresh Token、App Secret 不进入数据库。** 它们只从环境变量读取。

UI 新增「渠道与利润」页面，可：

- 新建渠道账号
- 检测真实连接
- 查看错误原因
- 查看最近同步时间
- 使用 `Mock` Safe Sandbox 做完整端到端验证

## 2. Shopify 真实连接

`ShopifyAdapter` 已从占位符升级为真实 Admin GraphQL 连接：

- `check_connection()`：读取 Shop 信息
- `publish_product()`：`productCreate`
- `update_price()`：`productVariantsBulkUpdate`
- `pull_orders()`：拉订单及 line items 并归一化

默认 API Version：`2026-07`。

环境变量：

```text
SHOPIFY_ACCESS_TOKEN=shpat_...
```

在 ChannelAccount 中填写：

```text
store_domain=your-store.myshopify.com
credential_env_prefix=SHOPIFY
```

## 3. Amazon SP-API 真实连接

V0.4 使用当前 Amazon SP-API 模式：

- LWA refresh token → access token
- Listings Items API 管理单 SKU listing
- Orders API v2026-01-01 作为订单同步目标
- `includedData=PROCEEDS,EXPENSE,PROMOTION` 预留更完整的财务信息

环境变量：

```text
AMAZON_SP_LWA_CLIENT_ID=...
AMAZON_SP_LWA_CLIENT_SECRET=...
AMAZON_SP_LWA_REFRESH_TOKEN=...
AMAZON_SP_DEFAULT_PRODUCT_TYPE=TOYS_AND_GAMES
```

ChannelAccount 填写：

```text
seller_id=...
marketplace_id=ATVPDKIKX0DER
credential_env_prefix=AMAZON_SP
config={"region":"NA"}
```

### Amazon 发布 Gate

JoyOPC **不会猜 Amazon Product Type Definition 属性**。若没有提供：

```json
{
  "amazon_product_type": "...",
  "amazon_attributes": {"...": "..."}
}
```

发布结果会是 `REQUIRES_CHANNEL_ATTRIBUTES`，而不是把一个不完整商品错误提交到真实账号。

## 4. TikTok Shop Open API 真实连接

V0.4 已实现：

- HTTPS gateway
- v202309+ path-style API
- HMAC request signing
- `x-tts-access-token`
- Authorized Shops 连接检测
- Create Product 请求
- Search Orders 请求和统一订单格式归一化
- Create Product idempotency key

环境变量：

```text
TIKTOK_SHOP_APP_KEY=...
TIKTOK_SHOP_APP_SECRET=...
TIKTOK_SHOP_ACCESS_TOKEN=...
```

TikTok 的叶子类目、类目规则、必填属性和合规字段具有市场差异，因此发布时必须传 `tiktok_payload`：

```json
{
  "tiktok_payload": {
    "title": "...",
    "category_id": "...",
    "skus": [],
    "...": "..."
  }
}
```

JoyOPC 不会绕过 TikTok Shop 的 Category Rules / Compliance Gate。

## 5. 商品发布：三区 Gate 仍然是第一道门

`POST /api/channels/publish` 只能发布已进入 `MasterProduct` 且决策为：

- `SCALE`
- `TEST`

若三区决策为：

- `HOLD`
- `REJECT`

API 返回 409，不允许直接把商品推入真实电商渠道。

也就是说 V0.4 的发布链是：

```text
Market Heat ≠ Publish

Market + 三区战略 + CEO Approval
             ↓
        Publish Gate
```

## 6. 订单真实回流 + 幂等

新增：

- `ChannelOrderLink`
- `CommerceOrderItem`
- `ChannelSyncRun`

同一个 `(ChannelAccount, external_order_id)` 再次同步时会更新原订单和 line items，而不会重复制造 GMV。

这对 Shopify/Amazon/TikTok 的轮询、Webhook 重试和断点续传非常关键。

## 7. SKU级真实贡献利润

JoyOPC 不把 GMV 当利润。

每个 SKU 统一计算：

```text
Net Sales
- Product Cost
- Shipping Cost
- Platform Fee
- Ad Cost
- Refund Cost
= Contribution Profit
```

V0.4 新增真实成本账本：`ChannelCostEntry`。

支持成本类型：

- `PLATFORM_FEE`
- `AD_SPEND`
- `SHIPPING`
- `REFUND`
- `OTHER`

成本可以按：

- external_order_id
- JoyOPC order_no
- SKU

归集。没有指定 SKU 的订单级成本会按照商品净销售额比例分摊到 line items。

### 利润质量

JoyOPC 会显示：

- `RECONCILED`：已经有足够的实际费用进入账本
- `PROVISIONAL`：成本数据仍不完整

这避免出现“订单已经同步，所以利润也一定真实”的错误结论。

## 8. 成本 CSV

先在 Safe Sandbox 点击「同步订单」，再上传：

`sample_data/channel_costs.csv`

即可验证：

```text
Mock Order
↓
JOY-AI-001
↓
平台费 + 广告费 + 物流
↓
SKU真实贡献利润重算
```

## 9. 运行

Windows PowerShell：

```powershell
cd JoyOPC_v0.4\apps\api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

进入：

**渠道与利润**

## 10. API

核心 V0.4 API：

```text
GET  /api/channels
POST /api/channels
POST /api/channels/{id}/check
POST /api/channels/publish
POST /api/channels/{id}/orders/sync
GET  /api/channel-sync-runs
GET  /api/orders
POST /api/costs
POST /api/costs/import
POST /api/profit/reconcile
GET  /api/profit/sku
GET  /api/commerce-control-center
POST /api/market/crawl
```

V0.1–V0.3 的选品、真实货盘、市场信号、多模态、CEO审批 API 全部保留。本机已接入的 AiSoul 公开页爬虫（弱市场信号）在 V0.4 上继续可用。

## 11. Tests

```powershell
cd JoyOPC_v0.4\apps\api
pytest -q
```

当前：V0.4 套件 + 本机 AiSoul 爬虫进气测试。

新增 V0.4 测试覆盖：

- Safe channel connection
- MasterProduct → Channel publish
- external object mapping
- order return
- repeated sync idempotency
- product cost mapping
- cost ledger reconciliation
- SKU contribution profit

## 12. 当前真实边界

已经真实落地：

- 渠道账号对象与凭证隔离
- Shopify Admin GraphQL HTTP 调用代码
- Amazon LWA / SP-API HTTP 调用代码
- TikTok Shop签名/HTTP调用代码
- 商品发布 Orchestration
- 订单统一模型与幂等 upsert
- SKU / MasterProduct 对齐
- 成本账本
- SKU贡献利润引擎
- UI 和审计运行记录

由于交付环境没有你的 Shopify / Amazon / TikTok Shop 生产账号密钥，**本次不能声称三个真实生产账号已经实调成功**。Safe Sandbox 已完整端到端验证；真实适配器会在配置真实授权后发出真实 API 请求，并把错误显式记录到 `ChannelSyncRun`。

## 官方接口参考

- Shopify Admin GraphQL / productCreate: https://shopify.dev/docs/api/admin-graphql/latest/mutations/productcreate
- Shopify productVariantsBulkUpdate: https://shopify.dev/docs/api/admin-graphql/latest/mutations/productVariantsBulkUpdate
- Amazon Orders API v2026-01-01: https://developer-docs.amazon.com/sp-api/docs/orders-api
- Amazon listing lifecycle: https://developer-docs.amazon.com/sp-api/lang-en_EN/docs/manage-product-listings-guide
- TikTok Shop API versioning: https://partner.tiktokshop.com/docv2/page/api-versioning
- TikTok Shop Products API: https://partner.tiktokshop.com/docv2/page/products-api-overview

详细设计见 `docs/V0.4_CHANNEL_COMMERCE.md`。
