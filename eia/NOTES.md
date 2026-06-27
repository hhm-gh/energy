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

energy schema                               # list all locally known paths (downloaded ● or schema-cached ○)
energy schema electricity/retail-sales      # schema + summary (fetches from API if not cached)
energy schema <path> --refresh              # re-fetch from API and recompute local stats
```

## Modules

| File | Purpose |
|------|---------|
| `client.py` | `EIAClient` — auth, HTTP, error handling |
| `inventory.py` | Recursive route traversal, rich tree display |
| `downloader.py` | Paginated fetch → Parquet, catalog management |
| `schema.py` | Schema fetch, local stat computation, display, caching |
| `storage.py` | Storage abstraction — `LocalStorage` (default) and `GCSStorage` (Phase 2 stub) |
| `cli.py` | argparse entry point for all commands |

## Storage abstraction (`storage.py`)

`downloader.py` and `schema.py` accept a `Storage` instance rather than a hard-coded path. This makes the storage backend swappable without touching business logic.

```python
class Storage(Protocol):
    def read_text(self, key: str) -> str: ...
    def write_text(self, key: str, content: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def find(self, filename: str) -> list[str]: ...   # returns relative key strings
    def uri(self, key: str) -> str: ...               # absolute path or gs://... URI
```

`LocalStorage("data")` is the default, constructed once at module level via `default_storage()`. `GCSStorage(bucket, prefix)` is the Phase 2 stub — `uri()` returns a `gs://` URI that pandas/pyarrow accept natively via gcsfs/fsspec.

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
      schema.json               cached schema — API metadata + computed local stats
```

`schema.json` is written in two situations: (1) by `energy schema <path>` on first call, and (2) automatically at the end of every `energy download`. It contains:
- API-sourced: name, description, frequencies, facets (id + description), column names and units, period bounds
- Computed from Parquet (if downloaded): actual period span, row count, per-column stats, unique facet values with human-readable labels

Numeric stats include both raw values and non-zero values (`min_nz`, `mean_nz`). Zero values in EIA data typically mean missing or not-applicable — sectors like transportation often have no reported rate — so raw means and minimums are misleading without filtering. The `Min (>0)` and `Mean (>0)` columns in the schema display make this visible. Note: `min_nz` can display as `0` for columns where the smallest non-zero value rounds down to zero (a rounding artifact, not a true zero).

Numbers in the schema display are rounded to the nearest integer and formatted with compact notation for large values (e.g., `166.4M`, `59k`).

Facet description columns follow no consistent EIA naming pattern. The schema module tries `{root}Description` then `{root}Name` (where root strips a trailing `id`), e.g. `stateid` → `stateDescription`, `sectorid` → `sectorName`.

## Known quirks

- `pd.to_numeric(errors="ignore")` was removed in pandas 2.2 — use `errors="coerce"` with a notna() guard to avoid clobbering non-numeric columns
- Some datasets are very large (crude-oil-imports: 550k+ rows); check `total` with a probe request before committing to a full download
- The EIA API occasionally returns `total` counts that drift slightly during pagination; the downloader breaks on empty page rather than relying on the total exactly
