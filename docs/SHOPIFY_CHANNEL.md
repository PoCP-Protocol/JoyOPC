# Shopify as a JoyOPC sales channel

Shopify is **not** the JoyOPC platform kernel. It is one Channel Gateway adapter.

JoyOPC always creates/updates listings as **Draft** (`status=draft`). It does not publish to the live storefront.

## Connect

1. Shopify Admin → Settings → Apps → Develop apps → Create an app.
2. Admin API scopes: `read_products`, `write_products`.
3. Install the app and copy the Admin API access token (`shpat_...`).
4. In JoyOPC → Foundation, paste:
   - shop domain: `your-store.myshopify.com`
   - access token
5. Click **连接 Shopify**, then **发布第一条 Master Product 草稿**.

Credentials are stored in the local JoyOPC `channel_accounts` table. API responses never return the token.

You can also put them in the repo-root `.env`:

```text
SHOPIFY_SHOP_URL=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_...
SHOPIFY_API_VERSION=2024-10
```

## APIs

- `POST /api/channels/shopify/connect`
- `POST /api/channels/shopify/publish-first-master`
- `POST /api/channels/shopify/publish_master/{id}`
