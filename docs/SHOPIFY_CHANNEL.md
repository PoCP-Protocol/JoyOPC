# Shopify as a JoyOPC sales channel

Shopify is **not** the JoyOPC platform kernel. It is one Channel Adapter behind JoyOPC Commerce Runtime.

JoyOPC always creates/updates listings as **Draft** (`status: DRAFT`). It does not publish to the live storefront.

## Connect

1. Shopify Admin → Settings → Apps and sales channels → Develop apps → Create an app.
2. Admin API scopes: `read_products`, `write_products`.
3. Install the app and copy the Admin API access token (`shpat_...`).
4. In JoyOPC → 渠道与利润, paste:
   - shop domain: `your-store.myshopify.com`
   - access token
5. Click **连接 Shopify**, then **发布第一条 Master Product 草稿**.

The token is written only to the gitignored repo-root `.env` as `SHOPIFY_ACCESS_TOKEN`. `ChannelAccount` stores the shop domain, never the token. API responses never return the token.

You can also put them in `.env` yourself and restart the API:

```text
SHOPIFY_SHOP_URL=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_...
SHOPIFY_API_VERSION=2026-07
```

Then click connection check on the Shopify account, or call `POST /api/channels/{id}/check`.

## Publish loop

1. Master Product must not be `HOLD` / `REJECT`.
2. Content Factory fills Shopify `descriptionHtml` / tags.
3. Adapter calls Admin GraphQL `productCreate` (or updates by SKU if the variant already exists).
4. Default variant SKU + price are set via `productVariantsBulkUpdate`.
5. `ChannelListing` + `ChannelObjectRef` store the Shopify product GID and admin URL.

Without credentials, the same path returns `DRY_RUN` with a draft payload. It does not pretend the listing is live.

## APIs

- `POST /api/channels/shopify/connect`
- `POST /api/channels/shopify/publish-first-master` (highest `opportunity_score`, always draft)
- `POST /api/channels/shopify/publish_master/{id}` (always draft)
- `POST /api/channels/publish` (commerce UI; keep **Draft** checked)
