# energy

CLI for querying U.S. Energy Information Administration (EIA) Open Data API v2.

## Setup

API key lives in macOS Keychain — no `.env` file:
```bash
security add-generic-password -a eia -s eia-api-key -w YOUR_KEY
# To rotate: add -U flag
```

Install deps: `pip install -r requirements.txt` (or use `.venv/`)

## Run

```bash
python main.py inventory                        # 2-level dataset tree
python main.py inventory --depth 3              # deeper traversal
python main.py inventory --path electricity     # drill into one category
python main.py inventory --descriptions         # include descriptions
python main.py inventory --flat                 # flat list of endpoints
```

## Structure

```
eia/client.py       EIAClient — auth (Keychain → env → .env), HTTP, errors
eia/inventory.py    Route tree traversal and rich tree display
main.py             CLI entry point
```

## API

Base URL: `https://api.eia.gov/v2/`  
Auth: `?api_key=` query param (injected by client)  
Route metadata: `GET /v2/{path}` → `response.routes[]`  
Data: `GET /v2/{path}/data` → `response.data[]`
