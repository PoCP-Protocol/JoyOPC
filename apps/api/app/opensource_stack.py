from __future__ import annotations

from typing import Any

from app.config import ROOT_DIR

VENDOR = ROOT_DIR / "vendor"

PACKAGES: list[dict[str, Any]] = [
    {
        "id": "saleor-platform",
        "role": "optional commerce kernel",
        "source": "https://github.com/saleor/saleor-platform",
        "license": "BSD-3",
        "vendor_dir": "saleor-platform",
        "mode": "compose",
        "borrow": "GraphQL kernel + Apps/webhooks. Do not fork Saleor core.",
    },
    {
        "id": "saleor-mcp",
        "role": "AI read-only Saleor",
        "source": "https://github.com/saleor/saleor-mcp",
        "license": "BSD-3",
        "vendor_dir": "saleor-mcp",
        "mode": "compose",
        "borrow": "Official MCP for catalog/order reads. Writes stay in JoyOPC.",
    },
    {
        "id": "open-listing-studio",
        "role": "listing field caps",
        "source": "https://github.com/clawnify/open-listing-studio",
        "license": "check vendor clone",
        "vendor_dir": "open-listing-studio",
        "mode": "reference",
        "borrow": "Amazon title/bullet/description/search-term limits in JoyOPC listing_limits.",
    },
    {
        "id": "openlinker",
        "role": "channel port factory",
        "source": "https://github.com/openlinker-project/openlinker",
        "license": "Apache-2.0",
        "vendor_dir": "openlinker",
        "mode": "reference",
        "borrow": "Per-connection adapter factory + identifier mapping. JoyOPC ChannelAdapter is the Python port.",
    },
    {
        "id": "kuberiva-oms",
        "role": "fulfillment sourcing strategies",
        "source": "https://github.com/KubeRiva/OMS",
        "license": "Apache-2.0",
        "vendor_dir": "kuberiva-oms",
        "mode": "reference",
        "borrow": "COST_OPTIMAL / DISTANCE / AI_ADAPTIVE vocabulary. Scoring uses JoyOPC SupplierProduct.",
    },
    {
        "id": "marketeer",
        "role": "SEA marketplace ports",
        "source": "https://github.com/codustry/marketeer",
        "license": "Apache-2.0",
        "vendor_dir": "marketeer",
        "mode": "watch",
        "borrow": "Shopee / Lazada / TikTok Shop as first-class ports. Clone is still design-phase; JoyOPC keeps TikTok adapter in-house.",
    },
    {
        "id": "trademind-ai",
        "role": "SKU bind + listing draft ops",
        "source": "https://github.com/lien0219/trademind-ai",
        "license": "Apache-2.0",
        "vendor_dir": "trademind-ai",
        "mode": "reference",
        "borrow": "Exact → normalized → similar SKU bind; never guess ambiguous matches. Do not run TradeMind as the OS.",
    },
    {
        "id": "ai-ecommerce-media-studio",
        "role": "product image + video storyboard",
        "source": "https://github.com/ronchen0927/AI-E-Commerce-Media-Studio",
        "license": "unspecified — reference only",
        "vendor_dir": "ai-ecommerce-media-studio",
        "mode": "reference",
        "borrow": "Hook/Demo/Proof/CTA storyboard. Local ffmpeg concat; Wan i2v stays opt-in.",
    },
    {
        "id": "product-card-processor",
        "role": "marketplace image cards",
        "source": "https://github.com/Ouple/product_card_processor",
        "license": "unspecified — reference only",
        "vendor_dir": "product-card-processor",
        "mode": "reference",
        "borrow": "Channel canvas sizes, product fit-on-card, optional rembg cutout.",
    },
    {
        "id": "rembg",
        "role": "optional neural background removal",
        "source": "https://github.com/danielgatis/rembg",
        "license": "MIT",
        "vendor_dir": "",
        "mode": "pip-optional",
        "borrow": "Enable with JOYOPC_REMBG=1 after pip install rembg. Default off.",
    },
    {
        "id": "python-amazon-sp-api",
        "role": "Amazon SP-API SDK",
        "source": "https://github.com/saleweaver/python-amazon-sp-api",
        "license": "MIT",
        "vendor_dir": "",
        "mode": "pip",
        "borrow": "Listings + Orders clients. JoyOPC AmazonAdapter remains the contract.",
    },
]


def amazon_sdk_status() -> dict[str, Any]:
    try:
        import sp_api  # noqa: F401

        return {"installed": True, "package": "python-amazon-sp-api"}
    except Exception:
        return {"installed": False, "package": "python-amazon-sp-api"}


def catalog() -> dict[str, Any]:
    rows = []
    for item in PACKAGES:
        dest = VENDOR / item["vendor_dir"] if item["vendor_dir"] else None
        rows.append(
            {
                **item,
                "cloned": bool(dest and dest.exists()),
                "path": str(dest) if dest else None,
            }
        )
    return {
        "rule": "JoyOPC composes OSS. It does not fork Saleor, Shopify, KubeRiva, or TradeMind into the kernel.",
        "packages": rows,
        "amazon_sdk": amazon_sdk_status(),
        "channel_ports": [
            {"channel": "Shopify", "status": "live-adapter", "inspired_by": "Shopify Admin GraphQL (not deprecated shopify_python_api REST)"},
            {"channel": "Amazon", "status": "live-adapter", "inspired_by": "python-amazon-sp-api + SP-API Listings/Orders"},
            {"channel": "TikTok Shop", "status": "live-adapter", "inspired_by": "Marketeer port model + official Open API HMAC"},
            {"channel": "Shopee", "status": "watch", "inspired_by": "codustry/marketeer"},
            {"channel": "Lazada", "status": "watch", "inspired_by": "codustry/marketeer"},
        ],
    }
