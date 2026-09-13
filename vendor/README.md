# JoyOPC vendor clones

Official / reference repositories are cloned here. **Do not fork and patch their cores.**

```powershell
powershell -File scripts/bootstrap_opensource.ps1
```

| Directory | Source | JoyOPC use |
|---|---|---|
| `saleor-platform` | github.com/saleor/saleor-platform | Commerce kernel runtime |
| `saleor-mcp` | github.com/saleor/saleor-mcp | Read-only AI access to Saleor |
| `open-listing-studio` | github.com/clawnify/open-listing-studio | Listing field-mapping reference |
| `openlinker` | github.com/openlinker-project/openlinker | Channel port / orchestration reference |

Python SDKs stay in pip: `python-amazon-sp-api`, `ShopifyAPI`.
