# energy

Tools for exploring and analyzing U.S. energy data from the EIA. Supports three data source types:

| Source | What it is | CLI commands |
|--------|-----------|--------------|
| **EIA Open Data API v2** | Live queryable series — electricity, gas, petroleum, coal, and more | `energy inventory`, `download`, `status`, `schema` |
| **Excel Publications** | Annual summary reports as downloadable `.xlsx` files (Electric Power Annual) | `energy pub-list`, `pub-download`, `pub-status` |
| **Bulk Files** | Complete dataset archives as ZIP files, updated twice daily | `energy bulk-list` |

## Overview

Three separate apps share a common Python core (`eia/`) that handles all data access and local storage:

| App | Command | Status |
|-----|---------|--------|
| CLI | `energy` | Available |
| TUI | `energy-tui` | Available |
| R Analysis | RStudio → `r/app.R` | Available |

Data flows one way: CLI/TUI fetch from EIA → local Parquet files → R reads locally.

---

## Setup

**1. Get an EIA API key** (free, required for API commands only)

Register at [eia.gov/opendata/register.php](https://www.eia.gov/opendata/register.php).

**2. Store the key in macOS Keychain**

```bash
security add-generic-password -a eia -s eia-api-key -w YOUR_KEY
```

To rotate: add `-U` to the same command.

**3. Install Python dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .          # CLI only
pip install -e ".[tui]"   # CLI + TUI
```

**4. Install R dependencies** (in RStudio, once)

```r
source("setup.R")
```

---

# CLI — API Datasets

The `energy` command browses the EIA v2 API dataset catalog, downloads datasets to local Parquet files, and displays schema summaries. An API key is required.

**`energy inventory`** — browse the EIA dataset tree

```bash
energy inventory                          # 2-level tree of all datasets
energy inventory --path electricity       # drill into a category
energy inventory --depth 3                # go deeper (more API calls)
energy inventory --descriptions           # include dataset descriptions
energy inventory --flat                   # flat list of queryable endpoints
```

**`energy download`** — fetch a dataset from the API and save locally as Parquet

```bash
energy download electricity/retail-sales  # download all rows
energy download <path> --frequency annual # specify frequency (default: first available)
```

**`energy status`** — table of all locally downloaded API datasets

```bash
energy status
```

**`energy schema`** — dataset structure, column units, value ranges, and facet values

```bash
energy schema                             # list all locally known paths
energy schema electricity/retail-sales    # full schema for a specific dataset
energy schema <path> --refresh            # re-fetch from API and recompute stats
```

Schema shows column min/max/mean with and without zeros — zero values in EIA data indicate missing or not-applicable rather than a genuine zero rate.

---

# CLI — Excel Publications

Annual summary reports published by EIA as Excel files. No API key required. Currently covers the **Electric Power Annual** (179 tables, 13 chapters). See `EXCEL-FILES.md` for full documentation.

> **Note on table IDs:** The `epa_` prefix in table IDs (e.g. `epa_11_03`) stands for **Electric Power Annual** — EIA's own abbreviation for this publication — not the Environmental Protection Agency.

**`energy pub-list`** — browse available tables

```bash
energy pub-list                           # all 179 tables, grouped by chapter
energy pub-list --chapter 11              # filter to one chapter (e.g. 11, A)
```

**`energy pub-download`** — download a table's Excel file and convert to Parquet

```bash
energy pub-download epa_11_03             # download by table id
energy pub-download epa_02_04             # average electricity price by sector
```

Tables with a single unambiguous header row are marked **clean** in their title and metadata. Multi-level merged-cell tables are marked **best-effort** — data values are reliable but column names may be verbose.

**`energy pub-status`** — table of all locally downloaded publication tables

```bash
energy pub-status
```

---

# CLI — Bulk Files

EIA publishes complete dataset histories as ZIP archives, updated twice daily. The manifest lists all available files. No API key required. See `BULK.md` for full documentation.

**`energy bulk-list`** — list all available bulk datasets from the live manifest

```bash
energy bulk-list                          # collapsed view (AEO years summarized)
energy bulk-list --aeo                    # expand all Annual Energy Outlook vintages
```

**AEO (Annual Energy Outlook):** EIA's flagship long-range forecast, published annually, projecting U.S. energy production, consumption, and trade ~25 years out. The bulk manifest carries 12 separate year-vintage files (2014–2026) because each edition is a standalone snapshot of what EIA projected that year — not an update to a running dataset. Researchers use the vintages to compare how forecasts evolved over time.

Available bulk datasets include: `ELEC`, `NG`, `PET`, `COAL`, `SEDS`, `STEO`, `TOTAL`, `INTL`, `EBA`, `EMISS`, `NUC_STATUS`, `PET_IMPORTS`, `IEO`, and AEO year-vintages.

---

# TUI

Interactive terminal UI built with [Textual](https://textual.textualize.io/). Browse the EIA dataset tree, view schema summaries, and download datasets with live progress — all from the terminal.

Install and launch:

```bash
pip install -e ".[tui]"
energy-tui
```

---

# R Analysis App

Interactive visualization of locally downloaded datasets in RStudio.

**Launch:**

1. Open `r/energy.Rproj` in RStudio
2. Run `source("setup.R")` once to install packages
3. Open `app.R` → click **Run App**

**Current app:** electricity rates by state — box-and-whisker plot with selectable states (all 62 states/territories) and sector filter, sourced from `electricity/retail-sales` monthly data (2001–present).

---

## Project Structure

```
eia/                Python core — shared by CLI and TUI
  client.py         EIA API client (auth, HTTP, error handling)
  inventory.py      API dataset tree traversal
  downloader.py     Paginated API download → Parquet
  schema.py         Schema fetch, stats, caching
  pub_catalog.py    Static catalog of Excel publications (Electric Power Annual)
  publications.py   Excel publication listing and display
  pub_downloader.py Excel download, parse, Parquet conversion, parse quality
  bulk.py           Bulk manifest fetch and display
  storage.py        Storage abstraction (LocalStorage / GCSStorage for Phase 2)
  cli.py            CLI entry point (all commands)
  NOTES.md          Developer notes

tui/                TUI app (Textual) — lazy tree, schema panel, download queue
r/                  R/Shiny analysis app
  NOTES.md          Developer notes

data/               Local dataset storage (gitignored)
  catalog.json      API dataset manifest
  pub_catalog.json  Excel publication manifest
  electricity/      API datasets
  publications/     Excel publication Parquet files

EXCEL-FILES.md      Excel publication documentation
BULK.md             Bulk file documentation
GUI-PLAN.md         TUI and browser GUI roadmap
TESTING.md          Test design and results
```

## Data Source Reference

| Source | Format | Key | Coverage |
|--------|--------|-----|----------|
| API v2 | JSON → Parquet | `energy download <path>` | All EIA series; queryable by facet/frequency |
| Electric Power Annual | Excel → Parquet | `energy pub-download epa_XX_XX` | Electricity only; 179 annual summary tables |
| Bulk files | ZIP (JSON) | listed by `energy bulk-list` | All major EIA topics; complete history |
