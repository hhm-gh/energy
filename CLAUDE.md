# energy

Three-app project for exploring and analyzing U.S. energy data from the EIA Open Data API v2.

| App | Entry point | Status |
|-----|------------|--------|
| CLI | `energy` | Available |
| TUI | `energy-tui` | Phase 1 — not yet built |
| R/Shiny | `r/app.R` in RStudio | Available |

All apps share `eia/` — the Python core handles API access, local storage, and the storage abstraction.  
See `GUI-PLAN.md` for the TUI and browser GUI roadmap.

## Architecture

```
energy/
  eia/            Python core — CLI, API client, downloader, schema, storage
  tui/            TUI app — Phase 1 (not yet built)
  r/              RStudio project (Shiny app, load helpers)
  data/           Local dataset storage — gitignored, written by CLI/TUI
  main.py         Dev shim (python main.py also works)
  pyproject.toml  Entry points: energy, energy-tui (once TUI is built)
```

Data flows one way: CLI/TUI download from EIA API → Parquet files in `data/` → R reads locally.

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
energy schema electricity/retail-sales
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

## Tests

```bash
pytest -m "not api"   # local tests only (~3s)
pytest -m api         # all tests, including live API calls (~45s)
```

See `TESTING.md` for test design and last run results.
