# energy

Tools for exploring and analyzing U.S. energy data from the [EIA Open Data API v2](https://www.eia.gov/opendata/).

**App 1 — Python CLI** (`energy`): browse the EIA dataset catalog and download datasets locally.  
**App 2 — R/Shiny** (`r/app.R`): interactive visualization of downloaded data in RStudio.

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
pip install -e .
```

**4. Install R dependencies** (in RStudio)

```r
# Open r/energy.Rproj, then run once:
source("setup.R")
```

## App 1 — CLI usage

```bash
energy inventory                          # browse all datasets (tree view)
energy inventory --path electricity       # drill into a category
energy inventory --descriptions           # show dataset descriptions
energy inventory --flat                   # flat list of queryable endpoints

energy download electricity/retail-sales  # download dataset → local Parquet
energy download <path> --frequency annual # specify frequency

energy status                             # show locally downloaded datasets
```

## App 2 — Shiny app

Open `r/energy.Rproj` in RStudio and click **Run App** on `app.R`.

Current app: electricity rates by state — box-and-whisker plot with selectable states and sector filter, sourced from `electricity/retail-sales` monthly data (2001–present).

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
eia/                Python package — API client, inventory, downloader, CLI
  NOTES.md          Developer notes: commands, API quirks, storage layout
r/                  RStudio project — Shiny visualization app
  NOTES.md          Developer notes: launch steps, data path convention
data/               Local dataset storage (gitignored, written by CLI)
main.py             Dev shim (python main.py also works)
pyproject.toml      Package definition → energy command
```
