# energy

A CLI for exploring and querying U.S. energy data via the [EIA Open Data API v2](https://www.eia.gov/opendata/).

## Setup

**1. Get an API key**

Register for free at [eia.gov/opendata/register.php](https://www.eia.gov/opendata/register.php).

**2. Store the key in macOS Keychain**

```bash
security add-generic-password -a eia -s eia-api-key -w YOUR_KEY
```

To rotate: add the `-U` (update) flag to the same command.

**3. Install**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
energy inventory                          # dataset tree (2 levels deep)
energy inventory --depth 3               # go deeper
energy inventory --path electricity      # drill into one category
energy inventory --descriptions          # include dataset descriptions
energy inventory --flat                  # flat list of queryable endpoints
```

## Dataset Coverage

The EIA API covers:

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
eia/
  client.py      HTTP client — Keychain auth, error handling
  inventory.py   Recursive route traversal, rich tree display
  cli.py         CLI entry point (argparse)
main.py          Dev shim (python main.py also works)
pyproject.toml   Package definition and script entry point
```
