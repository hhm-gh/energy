# EIA Bulk Files

EIA publishes a set of bulk download files — large ZIP archives containing complete dataset histories — separate from both the v2 API and the Excel publications. This document describes the bulk file capability added to the `energy` project.

---

## What Was Built

### Files added

| File | Purpose |
|------|---------|
| `eia/bulk.py` | `fetch_manifest()` fetches the live manifest; `print_bulk_list()` renders the dataset table |
| `eia/bulk_downloader.py` | Bulk ZIP download, NDJSON extraction, streaming parse → Parquet, catalog management |

### New CLI commands

| Command | Description |
|---------|-------------|
| `energy bulk-list` | List all bulk datasets from the live manifest (AEO years collapsed) |
| `energy bulk-list --aeo` | Expand all Annual Energy Outlook year-vintages as separate rows |
| `energy bulk-download <ID>` | Stream-download `<ID>.zip`, extract to `data/bulk/<ID>/raw.ndjson` |
| `energy bulk-parse <ID>` | Parse raw NDJSON → 4 Parquet files (series, series_meta, categories, category_series) |
| `energy bulk-status` | Table of all downloaded bulk datasets with parsed/not-parsed indicator |

### TUI integration

The `energy-tui` **Bulk tab** (press `2`) browses parsed bulk datasets interactively:

- Root level lists all downloaded+parsed datasets
- Expanding a dataset shows its root categories (loaded from `categories.parquet`)
- Expanding a category shows subcategories and series leaves (from `category_series.parquet`)
- Selecting any node shows metadata in the right panel (dataset stats, category child counts, or series name/units/frequency/geography/period)
- All navigation is local — no API key or network required
- Use `1` / `2` to switch between the API tab and Bulk tab

---

## The Manifest

EIA maintains a manifest file that describes every available bulk dataset:

```
https://www.eia.gov/opendata/bulk/manifest.txt
```

Despite the `.txt` extension, it is a JSON file with the structure:

```json
{
  "dataset": {
    "ELEC": {
      "name": "Electricity",
      "title": "Electricity",
      "description": "...",
      "temporal": "monthly, quarterly, annual",
      "spatial": "United States of America, state-level, plant-level",
      "accessURL": "https://www.eia.gov/opendata/bulk/ELEC.zip",
      "last_updated": "2026-06-25T02:00:58-04:00",
      ...
    },
    ...
  }
}
```

The manifest is updated twice daily at 5 a.m. and 3 p.m. ET. `fetch_manifest()` fetches it live on each call — it is small JSON (~50 KB) and not cached locally.

---

## Available Datasets (as of June 2026)

26 datasets total: 12 AEO year-vintages + 14 current datasets.

| ID | Name | Temporal |
|----|------|----------|
| AEO (12 vintages) | Annual Energy Outlook 2014–2026 | annual |
| AEO.IEO2 | International Energy Outlook 2023 | annual |
| COAL | Coal | quarterly, annual |
| EBA | U.S. Electric System Operating Data | hourly |
| ELEC | Electricity | monthly, quarterly, annual |
| EMISS | CO2 Emissions | annual |
| IEO | International Energy Outlook | annual |
| INTL | International Energy Data | annual |
| NG | Natural Gas | daily, weekly, monthly, quarterly, annual |
| NUC_STATUS | U.S. Nuclear Outages | daily |
| PET | Petroleum | daily, weekly, monthly, quarterly, annual |
| PET_IMPORTS | Crude Oil Imports | monthly, annual |
| SEDS | State Energy Data System | annual |
| STEO | Short-Term Energy Outlook | monthly, quarterly, annual |
| TOTAL | Total Energy | monthly, annual |

Download URL pattern: `https://www.eia.gov/opendata/bulk/<ID>.zip`

---

## A Note on AEO (Annual Energy Outlook)

**AEO** stands for **Annual Energy Outlook** — EIA's flagship long-range forecast report, published each year, projecting U.S. energy production, consumption, and trade out approximately 25 years. The bulk manifest carries 12 separate year-vintage files (currently 2014–2026) because each edition is preserved as a standalone download. These are not updates to the same dataset — each file is a complete snapshot of what EIA projected in that specific year, allowing researchers to compare forecasts across vintages and study how EIA's projections evolved over time.

---

## Plan — Future Capabilities

Phases 1–3 are complete. Remaining:

### Phase 2 — Download and extract ✓ Done

**New command:** `energy bulk-download <ID>`

Steps:
1. Look up `<ID>` in the live manifest (validates it exists, gets `accessURL` and `last_updated`)
2. Stream-download `<ID>.zip` to a temp file with a rich `DownloadColumn` progress bar (bytes downloaded / total)
3. Extract the single NDJSON file from the ZIP into `data/bulk/<ID>/raw.ndjson`
4. Write `data/bulk/<ID>/manifest.json` with id, name, description, temporal, spatial, last_updated, download URL, downloaded_at, raw file size, line count
5. Register in `data/bulk_catalog.json` (keyed by ID)

**New command:** `energy bulk-status`
- Print a table of downloaded bulk datasets: ID, name, temporal, raw file size, line count, downloaded date
- Mirrors the style of `energy status` and `energy pub-status`

Files created per download:
```
data/bulk/<ID>/raw.ndjson        ← extracted NDJSON, one record per line
data/bulk/<ID>/manifest.json     ← dataset metadata from manifest + download stats
data/bulk_catalog.json           ← index of all downloaded bulk datasets
```

**NDJSON record format (from EIA):**

Every line is one of three record types, identified by which ID key is present:

```json
// Series record — has "series_id"; contains the actual time-series data
{"series_id": "EMISS.CO2-TOTV-CC-CO-AK.A", "name": "...", "units": "...",
 "f": "A", "geography": "USA-AK", "start": "1970", "end": "2022",
 "geoset_id": "EMISS.CO2-TOTV-CC-CO.A",   // back-reference to geoset group (optional)
 "data": [["2022", 1234.5], ["2021", 1200.0], ...]}

// Category record — has "category_id"; describes a node in EIA's browse hierarchy
// parent_category_id is on the record itself (observed in EMISS)
// childseries is a flat list of series ID strings (not dicts)
{"category_id": "2251607", "parent_category_id": "2251604",
 "name": "Commercial sector CO2 emissions",
 "notes": "...",
 "childcategories": [],
 "childseries": ["EMISS.CO2-TOTV-CC-CO-AK.A", "EMISS.CO2-TOTV-CC-CO-AL.A", ...]}

// Geoset record — has "geoset_id" only; a lightweight descriptor grouping
// geographically-related series (e.g. the same metric across all states)
{"geoset_id": "EMISS.CO2-TOTV-CC-CO.A",
 "name": "Commercial sector CO2 emissions by state",
 "units": "Million Metric Tons of CO2"}
```

Notes on format variation (observed from EMISS, may differ across datasets):
- `parent_category_id` may appear directly on category records, or may need to be inferred from `childcategories` listings on parent records
- `childseries` may be a flat list of strings or a list of dicts — the parser handles both
- Series records that belong to a geoset carry a `geoset_id` back-reference alongside their `series_id`
- Geoset records are skipped during parse (no data arrays); they are informational grouping metadata only

### Phase 3 — Parse and convert ✓ Done

**New command:** `energy bulk-parse <ID>`

Reads `data/bulk/<ID>/raw.ndjson` and writes two Parquet files:

```
data/bulk/<ID>/series.parquet      ← one row per (series_id, period) — the time-series data
data/bulk/<ID>/series_meta.parquet ← one row per series_id — metadata (name, units, f, geography, ...)
```

**`series.parquet` schema** (flattened from `data` arrays):

| column | type | notes |
|--------|------|-------|
| `series_id` | string | e.g. `ELEC.SALES.AK-ALL.A` |
| `period` | string | as-is from EIA (e.g. `"2023"`, `"2023-01"`, `"20230101"`) |
| `value` | float64 | nullable — EIA uses `None` for missing values |

**`series_meta.parquet` schema** (one row per series, from the series record header):

| column | type |
|--------|------|
| `series_id` | string |
| `name` | string |
| `units` | string |
| `f` | string (frequency code: A/Q/M/W/D/H) |
| `geography` | string |
| `start` | string |
| `end` | string |

**Category storage** — category records are written to two flat Parquet tables. This supports both TUI navigation (load into an in-memory dict keyed by `category_id`) and R analysis (standard `dplyr` joins):

```
data/bulk/<ID>/categories.parquet       ← one row per category node
data/bulk/<ID>/category_series.parquet  ← junction: category → series membership
```

**`categories.parquet` schema:**

| column | type | notes |
|--------|------|-------|
| `category_id` | string | |
| `name` | string | human-readable label |
| `parent_category_id` | string, nullable | null = root node |

**`category_series.parquet` schema** (junction table — a series may appear under multiple categories):

| column | type |
|--------|------|
| `category_id` | string |
| `series_id` | string |

**R access pattern:**
```r
cats    <- arrow::read_parquet("data/bulk/ELEC/categories.parquet")
cat_ser <- arrow::read_parquet("data/bulk/ELEC/category_series.parquet")
meta    <- arrow::read_parquet("data/bulk/ELEC/series_meta.parquet")

# All series under a category (with labels)
cat_ser |>
  dplyr::filter(category_id == "711224") |>
  dplyr::left_join(meta, by = "series_id")
```

**TUI access pattern** — load at startup, build a dict for O(1) navigation:
```python
cats_df    = pd.read_parquet("data/bulk/ELEC/categories.parquet")
cat_ser_df = pd.read_parquet("data/bulk/ELEC/category_series.parquet")

# Build tree dict
tree = {row.category_id: {"name": row.name, "parent": row.parent_category_id, "children": [], "series": []}
        for row in cats_df.itertuples()}
for row in cat_ser_df.itertuples():
    tree[row.category_id]["series"].append(row.series_id)
# child lists populated from parent_category_id grouping
```

**Full output layout for `energy bulk-parse <ID>`:**
```
data/bulk/<ID>/series.parquet           ← time-series data (series_id, period, value)
data/bulk/<ID>/series_meta.parquet      ← one row per series (name, units, f, geography, ...)
data/bulk/<ID>/categories.parquet       ← category tree nodes
data/bulk/<ID>/category_series.parquet  ← category → series membership
```

**Streaming parse approach** — bulk files can be large (EBA is ~1 GB). Parse line-by-line without loading everything into memory:
- Accumulate `series.parquet` in chunks (e.g. 100k rows), write with pyarrow in append mode
- Accumulate `series_meta`, `categories`, and `category_series` rows in memory (counts of rows, not data arrays — manageable)
- Show a progress bar (lines processed / total lines from manifest.json)

**Storage layout rationale** — one file per dataset rather than splitting by series prefix. Keeps query patterns simple: `pd.read_parquet(..., filters=[("series_id", "in", ids)])` with pyarrow predicate pushdown handles selective reads efficiently. If a dataset is too large to work with in R, the Phase 4 filter step addresses it.

### Phase 4 — Query and filter

Bulk files contain far more data than most analyses need. A filter step on ingest (by series ID prefix, geography, or date range) would keep local storage manageable.

---

## Relationship to Other Source Types

| Source | Access | Format | Granularity | Update cadence |
|--------|--------|--------|-------------|----------------|
| v2 API (`energy download`) | Live HTTP, paginated | JSON → Parquet | Queryable by facet/frequency | Near real-time |
| Excel publications (`energy pub-download`) | Direct `.xlsx` download | Excel → Parquet | Annual summary tables | Publication cycle |
| Bulk files (`energy bulk-download`) | ZIP → NDJSON | Newline-delimited JSON → Parquet | Complete history, all series | Twice daily |

Bulk files are best suited for: complete dataset pulls, offline analysis, and avoiding API rate limits. The v2 API is better for targeted queries on specific series or facets.
