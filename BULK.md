# EIA Bulk Files

EIA publishes a set of bulk download files — large ZIP archives containing complete dataset histories — separate from both the v2 API and the Excel publications. This document describes the bulk file capability added to the `energy` project.

---

## What Was Built

### Files added

| File | Purpose |
|------|---------|
| `eia/bulk.py` | `fetch_manifest()` fetches the live manifest; `print_bulk_list()` renders the dataset table |

### New CLI commands

| Command | Description |
|---------|-------------|
| `energy bulk-list` | List all bulk datasets from the live manifest (AEO years collapsed) |
| `energy bulk-list --aeo` | Expand all Annual Energy Outlook year-vintages as separate rows |

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

The listing capability implemented here is phase 1. Logical next steps:

### Phase 2 — Download and extract

- `energy bulk-download <ID>` — download `<ID>.zip` to `data/bulk/<ID>/`, extract the JSON data file inside
- Progress bar (files can be large: ELEC and EBA are several hundred MB)
- Track downloaded bulk files in `data/bulk_downloads.json`

### Phase 3 — Parse and convert

Each bulk ZIP contains a single newline-delimited JSON file where each line is either a category record or a series record. Converting to Parquet requires:
- Splitting category vs. series records
- Flattening series data (each series has a `data` array of `[period, value]` pairs)
- Deciding on storage layout (one Parquet per series group, or one large file)

### Phase 4 — Query and filter

Bulk files contain far more data than most analyses need. A filter step on ingest (by series ID prefix, geography, or date range) would keep local storage manageable.

---

## Relationship to Other Source Types

| Source | Access | Format | Granularity | Update cadence |
|--------|--------|--------|-------------|----------------|
| v2 API (`energy download`) | Live HTTP, paginated | JSON → Parquet | Queryable by facet/frequency | Near real-time |
| Excel publications (`energy pub-download`) | Direct `.xlsx` download | Excel → Parquet | Annual summary tables | Publication cycle |
| Bulk files (`energy bulk-list`) | ZIP download | Newline-delimited JSON | Complete history, all series | Twice daily |

Bulk files are best suited for: complete dataset pulls, offline analysis, and avoiding API rate limits. The v2 API is better for targeted queries on specific series or facets.
