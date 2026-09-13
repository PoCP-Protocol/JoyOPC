# JoyOPC Architecture v0.4

JoyOPC is an AI-native OPC Commerce OS. It is not a storefront and not an ERP fork.

```text
CEO Cockpit
    |
AI Workforce / Decision Runtime
    |
JoyOPC Commerce Runtime
    |-- Product Master
    |-- Supplier Product
    |-- Product Zone Engine
    |-- Real Data + Multimodal
    |-- Channel Accounts
    |-- Channel Publishing
    |-- Unified Order + Order Item
    |-- Cost Ledger
    |-- SKU Profit Runtime
    |
Channel Gateway ---------------------- Saleor Adapter (optional)
    |                                      |
Shopify / Amazon / TikTok Shop        Commerce Kernel
```

## Boundary rule

JoyOPC owns:

- OPC company model
- Product Master
- 产品三区与经营策略
- AI agents and approvals
- channel orchestration
- cross-channel identity mapping
- idempotent order return
- contribution profit intelligence
- product/content intelligence

External platforms own:

- marketplace/shop account state
- platform listing review
- platform order facts
- platform fulfillment facts
- platform settlement/ads source records

Secrets remain outside the database and are resolved at runtime from environment variables.
