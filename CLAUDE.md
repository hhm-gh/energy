# energy

Two-app project for exploring and analyzing U.S. energy data from the EIA Open Data API v2.

**App 1 — Python CLI** (`energy`): browse the EIA dataset catalog and download datasets to local Parquet files.  
**App 2 — R/Shiny** (`r/app.R`): interactive visualization of locally downloaded datasets.

## Architecture

```
energy/
  eia/            Python package (CLI, API client, downloader)
  r/              RStudio project (Shiny app, load helpers)
  data/           Local dataset storage — gitignored, written by CLI
  main.py         Dev shim (python main.py also works)
  pyproject.toml  Package entry point → `energy` command
```

Data flows one way: CLI downloads from EIA API → Parquet files in `data/` → R reads locally.

See `eia/NOTES.md` for Python CLI details and `r/NOTES.md` for the R app.

## Quick start

**Python CLI**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
security add-generic-password -a eia -s eia-api-key -w YOUR_KEY  # once
energy inventory
energy download electricity/retail-sales
energy status
```

**R / Shiny**
```
Open r/energy.Rproj in RStudio
source("setup.R")   # once — installs packages via renv
# open app.R → Run App
```

## API key

Stored in macOS Keychain — no `.env` file. Client checks Keychain first, then `EIA_API_KEY` env var.  
To rotate: `security add-generic-password -U -a eia -s eia-api-key -w NEW_KEY`
