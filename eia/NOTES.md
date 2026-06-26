# Python CLI — developer notes

## Commands

```bash
energy inventory                            # 2-level dataset tree
energy inventory --depth 3                  # deeper (more API calls)
energy inventory --path electricity         # drill into one category
energy inventory --descriptions             # show route descriptions
energy inventory --flat                     # flat list of queryable endpoints

energy download electricity/retail-sales    # download all rows → Parquet
energy download <path> --frequency annual   # override default frequency

energy status                               # table of locally downloaded datasets
```

## Modules

| File | Purpose |
|------|---------|
| `client.py` | `EIAClient` — auth, HTTP, error handling |
| `inventory.py` | Recursive route traversal, rich tree display |
| `downloader.py` | Paginated fetch → Parquet, catalog management |
| `cli.py` | argparse entry point for all commands |

## EIA API v2

- Base URL: `https://api.eia.gov/v2/`
- Auth: `?api_key=` query param — injected by `EIAClient`, never hardcoded
- Route metadata: `GET /v2/{path}` → `response.routes[]` (child routes) or leaf info
- Data: `GET /v2/{path}/data` → `response.data[]`, max 5,000 rows per request
- Frequency param takes the `id` string (`"monthly"`, `"annual"`) — not the `query` shorthand (`"M"`, `"A"`)

## Local storage layout

```
data/
  catalog.json                  manifest of all downloaded datasets
  electricity/
    retail-sales/
      data.parquet              all rows, numeric data columns coerced to float
      metadata.json             name, frequency, facets, row count, downloaded_at
```

## Known quirks

- `pd.to_numeric(errors="ignore")` was removed in pandas 2.2 — use `errors="coerce"` with a notna() guard to avoid clobbering non-numeric columns
- Some datasets are very large (crude-oil-imports: 550k+ rows); check `total` with a probe request before committing to a full download
- The EIA API occasionally returns `total` counts that drift slightly during pagination; the downloader breaks on empty page rather than relying on the total exactly
