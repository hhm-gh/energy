# energy

Tools for exploring and analyzing U.S. energy data from the [EIA Open Data API v2](https://www.eia.gov/opendata/).

## Overview

Three separate apps share a common Python core (`eia/`) that handles all API access and local data storage:

| App | Command | Status |
|-----|---------|--------|
| CLI | `energy` | Available |
| TUI | `energy-tui` | Planned — Phase 1 |
| R Analysis | RStudio → `r/app.R` | Available |

Data flows one way: CLI/TUI download from EIA API → local Parquet files → R reads locally.

---

## Setup

**1. Get an EIA API key** (free)

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
pip install -e ".[tui]"   # CLI + TUI (once TUI is built)
```

**4. Install R dependencies** (in RStudio, once)

```r
source("setup.R")
```

---

# CLI

The `energy` command browses the EIA dataset catalog, downloads datasets to local Parquet files, and displays schema summaries.

**`energy inventory`** — browse the EIA dataset tree

```bash
energy inventory                          # 2-level tree of all datasets
energy inventory --path electricity       # drill into a category
energy inventory --depth 3               # go deeper (more API calls)
energy inventory --descriptions           # include dataset descriptions
energy inventory --flat                   # flat list of queryable endpoints
```

**`energy download`** — fetch a dataset from the API and save locally as Parquet

```bash
energy download electricity/retail-sales  # download all rows
energy download <path> --frequency annual # specify frequency (default: first available)
```

**`energy status`** — table of all locally downloaded datasets

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

# TUI

> **Status: Phase 1 — planned, not yet built.** See `GUI-PLAN.md` for the full design.

The `energy-tui` command will provide an interactive terminal UI for the same functions available in the CLI: browsing the dataset tree, viewing schema summaries, and selecting multiple datasets for download with real-time progress display.

Built with [Textual](https://textual.textualize.io/). Install when available:

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

## Dataset Coverage

| Category | Examples |
|----------|---------|
| Electricity | Retail sales, generation, hourly RTO operations, generator inventory |
| Natural Gas | Prices, production, storage, imports/exports |
| Petroleum | Prices, refining, crude reserves, stocks |
| Coal | Production, shipments, prices, reserves |
| Nuclear | Plant and generator-level outage data |
| Total Energy | Cross-source integrated statistics |
| SEDS | State-level data for all energy types |
| STEO | 18-month short-term projections |
| AEO / IEO | Annual and international long-term outlooks |
| Densified Biomass | Capacity, production, sales |

## Project Structure

```
eia/                Python core — shared by CLI and TUI
  storage.py        Storage abstraction (LocalStorage / GCSStorage for Phase 2)
  client.py         EIA API client
  inventory.py      Dataset tree traversal
  downloader.py     Paginated download → Parquet
  schema.py         Schema fetch, stats, caching
  cli.py            CLI entry point
  NOTES.md          Developer notes
tui/                TUI app — Phase 1 (not yet built)
r/                  R/Shiny analysis app
  NOTES.md          Developer notes
data/               Local dataset storage (gitignored)
GUI-PLAN.md         TUI and browser GUI roadmap
TESTING.md          Test design and results
```
