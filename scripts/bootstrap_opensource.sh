#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/vendor"
mkdir -p "$VENDOR"

clone() {
  local url="$1" dest="$2"
  if [ -d "$dest" ]; then
    echo "skip (exists): $dest"
    return
  fi
  git clone --depth 1 "$url" "$dest"
}

clone "https://github.com/saleor/saleor-platform.git" "$VENDOR/saleor-platform"
clone "https://github.com/saleor/saleor-mcp.git" "$VENDOR/saleor-mcp"
clone "https://github.com/clawnify/open-listing-studio.git" "$VENDOR/open-listing-studio"
clone "https://github.com/openlinker-project/openlinker.git" "$VENDOR/openlinker"
clone "https://github.com/KubeRiva/OMS.git" "$VENDOR/kuberiva-oms"
clone "https://github.com/codustry/marketeer.git" "$VENDOR/marketeer"
clone "https://github.com/lien0219/trademind-ai.git" "$VENDOR/trademind-ai"
clone "https://github.com/ronchen0927/AI-E-Commerce-Media-Studio.git" "$VENDOR/ai-ecommerce-media-studio"
clone "https://github.com/Ouple/product_card_processor.git" "$VENDOR/product-card-processor"

cat <<'EOF'

Vendor clones ready. Do not fork or patch Saleor Core.
Python SDKs: pip install -r apps/api/requirements.txt
JoyOPC API should use port 8100 if Saleor occupies 8000.
EOF
