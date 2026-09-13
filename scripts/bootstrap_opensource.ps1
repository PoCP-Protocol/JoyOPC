$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Vendor = Join-Path $Root "vendor"
New-Item -ItemType Directory -Force -Path $Vendor | Out-Null

function Get-Repo([string]$Url, [string]$Dest) {
  if (Test-Path $Dest) {
    Write-Host "skip (exists): $Dest"
    return
  }
  git clone --depth 1 $Url $Dest
}

Get-Repo "https://github.com/saleor/saleor-platform.git" (Join-Path $Vendor "saleor-platform")
Get-Repo "https://github.com/saleor/saleor-mcp.git" (Join-Path $Vendor "saleor-mcp")
Get-Repo "https://github.com/clawnify/open-listing-studio.git" (Join-Path $Vendor "open-listing-studio")
Get-Repo "https://github.com/openlinker-project/openlinker.git" (Join-Path $Vendor "openlinker")
Get-Repo "https://github.com/KubeRiva/OMS.git" (Join-Path $Vendor "kuberiva-oms")
Get-Repo "https://github.com/codustry/marketeer.git" (Join-Path $Vendor "marketeer")
Get-Repo "https://github.com/lien0219/trademind-ai.git" (Join-Path $Vendor "trademind-ai")
Get-Repo "https://github.com/ronchen0927/AI-E-Commerce-Media-Studio.git" (Join-Path $Vendor "ai-ecommerce-media-studio")
Get-Repo "https://github.com/Ouple/product_card_processor.git" (Join-Path $Vendor "product-card-processor")

Write-Host ""
Write-Host "Vendor clones ready. Do not fork or patch Saleor Core."
Write-Host "Python SDKs: pip install -r apps/api/requirements.txt"
Write-Host "JoyOPC API should use port 8100 if Saleor occupies 8000."
