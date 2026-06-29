# energy

Three-app project for exploring and analyzing U.S. energy data from the EIA. Supports three data source types: the v2 API, Excel publications, and bulk file archives.

| App | Entry point | Status |
|-----|------------|--------|
| CLI | `energy` | Available |
| TUI | `energy-tui` | Available |
| R/Shiny | `r/app.R` in RStudio | Available |

All apps share `eia/` — the Python core handles API access, Excel publication downloads, bulk file download/parse, local storage, and the storage abstraction.  
See `GUI-PLAN.md` for the TUI and browser GUI roadmap.

## Architecture

```
energy/
  eia/            Python core — CLI, API client, downloader, schema, publications, bulk, storage
  tui/            TUI app (Textual)
  r/              RStudio project (Shiny app, load helpers)
  data/           Local dataset storage — gitignored, written by CLI/TUI
  main.py         Dev shim (python main.py also works)
  pyproject.toml  Entry points: energy, energy-tui
```

Data flows one way: CLI/TUI fetch from EIA → Parquet files in `data/` → R reads locally.

See `eia/NOTES.md` for Python CLI details and `r/NOTES.md` for the R app.

## Modules

| File | Purpose |
|------|---------|
| `eia/client.py` | `EIAClient` — auth, HTTP, error handling |
| `eia/inventory.py` | Recursive route traversal, rich tree display |
| `eia/downloader.py` | Paginated API fetch → Parquet, catalog management |
| `eia/schema.py` | Schema fetch, local stat computation, display, caching |
| `eia/pub_catalog.py` | Static catalog of the Electric Power Annual (179 tables, 13 chapters) |
| `eia/publications.py` | Excel publication listing and chapter-grouped display |
| `eia/pub_downloader.py` | Excel download, best-effort parse → Parquet, parse quality tracking |
| `eia/bulk.py` | Bulk manifest fetch and dataset listing |
| `eia/bulk_downloader.py` | Bulk ZIP download → NDJSON, parse → Parquet, catalog management |
| `eia/storage.py` | Storage abstraction — `LocalStorage` (default) and `GCSStorage` (Phase 2 stub) |
| `eia/cli.py` | argparse entry point for all commands |

## Quick start

**Python CLI — API datasets**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
security add-generic-password -a eia -s eia-api-key -w YOUR_KEY  # once
energy inventory
energy download electricity/retail-sales
energy status
energy schema electricity/retail-sales
```

**Python CLI — Excel publications**
```bash
energy pub-list                     # browse 179 Electric Power Annual tables
energy pub-list --chapter 11        # filter by chapter
energy pub-download epa_11_03       # download → Parquet
energy pub-status                   # show downloaded publication tables
```

**Python CLI — Bulk files**
```bash
energy bulk-list                    # list all bulk datasets from live manifest
energy bulk-list --aeo              # expand AEO year-vintages
energy bulk-download EMISS          # download ZIP → data/bulk/EMISS/raw.ndjson
energy bulk-parse EMISS             # parse NDJSON → 4 Parquet files
energy bulk-status                  # show downloaded/parsed bulk datasets
```

**R / Shiny**
```
Open r/energy.Rproj in RStudio
source("setup.R")   # once — installs packages via renv
# open app.R → Run App
```

## API key

Stored in macOS Keychain — no `.env` file. Required for API commands (`inventory`, `download`, `schema`). Not needed for `pub-*` or `bulk-*` commands.  
Client checks Keychain first, then `EIA_API_KEY` env var.  
To rotate: `security add-generic-password -U -a eia -s eia-api-key -w NEW_KEY`

## Tests

```bash
pytest -m "not api"   # local tests only (~3s)
pytest -m api         # all tests, including live API calls (~45s)
```

Tests cover `inventory` and `schema` commands. The `pub-*` and `bulk-*` commands have no automated tests yet.

See `TESTING.md` for test design and last run results.

## Documentation

| File | Covers |
|------|--------|
| `eia/NOTES.md` | Python CLI developer details, API quirks, storage layout |
| `r/NOTES.md` | R/Shiny app details |
| `EXCEL-FILES.md` | Excel publication architecture, parse quality system, Electric Power Annual chapter list |
| `BULK.md` | Bulk file manifest, dataset list, future download/parse roadmap |
| `GUI-PLAN.md` | TUI and browser GUI (Phase 2) roadmap |
| `TESTING.md` | Test design, coverage, and last run results |
