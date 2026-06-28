# EIA Excel Publications

This document covers the Excel-based EIA datasets added to the `energy` project alongside the existing v2 API datasets.

## Scope

**This covers electricity datasets only.** The EIA publishes Excel-based data across many energy categories following the same general pattern, but only electricity has been inventoried here. Other categories — petroleum, natural gas, coal, nuclear, renewables — require their index pages to be discovered and their table catalogs to be built separately. See [Other Categories](#other-categories) below.

---

## What Was Built

### Files added

| File | Purpose |
|------|---------|
| `eia/pub_catalog.py` | Static catalog — all 179 tables from the Electric Power Annual, organized by chapter |
| `eia/publications.py` | Display logic — `list_tables()` and `print_pub_list()` for the CLI listing |
| `eia/pub_downloader.py` | Download and parse — fetches `.xlsx`, converts to Parquet, tracks parse quality |

### New CLI commands

| Command | Description |
|---------|-------------|
| `energy pub-list` | List all 179 tables, grouped by chapter |
| `energy pub-list --chapter 11` | Filter by chapter number (`11`, `A`, etc.) |
| `energy pub-download epa_11_03` | Download one table by id → Parquet |
| `energy pub-download epa_02_04 --pub electricity-annual` | Explicit publication (default: electricity-annual) |
| `energy pub-status` | Show all locally downloaded publication tables |

---

## URL Patterns

The Electric Power Annual lives at `https://www.eia.gov/electricity/annual/`. Every table has two URLs built from its id (e.g. `epa_11_03`):

```
HTML viewer:  https://www.eia.gov/electricity/annual/table.php?t=epa_11_03.html
Excel file:   https://www.eia.gov/electricity/annual/xls/epa_11_03.xlsx
```

The id encodes the chapter and table number: `epa_<chapter>_<table>`, with letter suffixes for sub-tables (e.g. `epa_03_01_a`).

> **Note — `epa_` prefix:** In EIA's own naming convention, `epa` stands for **Electric Power Annual** (the name of this publication), not the Environmental Protection Agency. All 179 table ids use this prefix.

---

## Storage Layout

Downloaded publication tables follow the same `data/` root as API datasets but under a `publications/` prefix:

```
data/
  pub_catalog.json                          manifest of all downloaded pub tables
  publications/
    electricity-annual/
      epa_11_03/
        data.parquet                        parsed data, all numeric cols as float64
        metadata.json                       table info, source URL, parse quality, column list
      epa_02_04/
        data.parquet
        metadata.json
```

`metadata.json` fields:

```json
{
  "pub_id": "electricity-annual",
  "pub_title": "Electric Power Annual",
  "table_id": "epa_02_04",
  "table_number": "2.4",
  "table_title": "Average price of electricity to ultimate customers by end-use sector (clean)",
  "chapter_number": "2",
  "chapter_title": "Electricity Sales",
  "source_url": "https://www.eia.gov/electricity/annual/xls/epa_02_04.xlsx",
  "parse_quality": "clean",
  "rows": 55,
  "columns": ["Year", "Residential", "Commercial", "Industrial", "Transportation", "Total"],
  "downloaded_at": "2026-06-28T..."
}
```

---

## Parse Quality

EIA Excel files have varied internal structure. The parser (`pub_downloader.parse_xlsx`) applies a best-effort heuristic:

1. Find the first row where any cell in columns 1+ is a float — this is the data boundary.
2. Collect header rows between the title row and the data boundary (skipping single-cell section labels).
3. Forward-fill `None` values within each header row (handling merged cells).
4. For each column, join the unique non-duplicate level labels with ` / `.

**Parse quality is determined by the number of header rows found:**

| Quality | Condition | Meaning |
|---------|-----------|---------|
| `clean` | Exactly 1 header row | Column names are unambiguous. The parser found a single, definitive header row — column names can be trusted exactly as written. The word "clean" is appended to the title in metadata and `pub_catalog.json`. |
| `best-effort` | 2 or more header rows | The table uses multi-level merged-cell headers. The parser joins the levels heuristically. Data values are likely correct, but column names may be verbose or have minor inaccuracies where forward-fill carried a parent label too far. |

### Tested tables

| Table | Parse quality | Notes |
|-------|--------------|-------|
| `epa_02_04` — Average price of electricity, by sector | **clean** | Single header row, 6 columns |
| `epa_11_03` — Reliability metrics by state | best-effort | 3 header rows, 15 columns including multi-level SAIDI/SAIFI/CAIDI groupings |

Quality is stamped at download time and visible in `energy pub-status` (Quality column) and in each table's `metadata.json`.

---

## Electric Power Annual — Chapter Summary

179 tables across 13 chapters. Run `energy pub-list` to see the full listing.

| Chapter | Title | Tables |
|---------|-------|--------|
| 1 | National Summary Data | 3 |
| 2 | Electricity Sales | 14 |
| 3 | Net Generation | 27 |
| 4 | Generation Capacity | 20 |
| 5 | Consumption of Fossil Fuels | 44 |
| 6 | Fossil Fuel Stocks for Electricity Generation | 4 |
| 7 | Receipts, Cost, and Quality of Fossil Fuels | 25 |
| 8 | Electric Power System Characteristics and Performance | 4 |
| 9 | Environmental Data | 5 |
| 10 | Energy Efficiency, Demand Response and Advanced Meters | 5 |
| 11 | Distribution System Reliability | 6 |
| 12 | U.S. Territories | 8 |
| A | Appendices | 5 |

---

## Other Categories

The EIA publishes Excel-based data for many energy categories beyond electricity. The general URL pattern is:

```
https://www.eia.gov/<category>/
```

Known categories that likely follow the same structure:

| Category | Index URL |
|----------|-----------|
| Petroleum | `https://www.eia.gov/petroleum/` |
| Natural Gas | `https://www.eia.gov/naturalgas/` |
| Coal | `https://www.eia.gov/coal/` |
| Nuclear | `https://www.eia.gov/nuclear/` |
| Renewable Energy | `https://www.eia.gov/renewable/` |
| Environment | `https://www.eia.gov/environment/` |

**Each of these needs to be discovered separately.** The index page structure and table naming conventions may differ from the Electric Power Annual. To add a new category:

1. Fetch the category index page and locate the table listing.
2. Add a new publication dict to `eia/pub_catalog.py` following the `ELECTRICITY_ANNUAL` pattern.
3. Register it in `ALL_PUBLICATIONS`.
4. The download and parse pipeline in `pub_downloader.py` is generic and will work without modification, subject to the same parse-quality caveats.

---

## Relationship to API Datasets

The v2 API and Excel publications are complementary, not overlapping:

- **API datasets** (`energy inventory`, `energy download`): machine-readable, paginated, queryable by facet and frequency. Updated frequently. Accessed via `api.eia.gov/v2/`.
- **Excel publications** (`energy pub-list`, `energy pub-download`): annual summary reports, richer cross-sectional structure (multi-year, multi-sector tables), but static snapshots updated on publication release cycles. Accessed via `eia.gov/electricity/annual/xls/`.

Both land in `data/` as Parquet files and can be read identically in R with `arrow::read_parquet()`.
