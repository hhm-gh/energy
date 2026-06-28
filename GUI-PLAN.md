# App Plan

## Terminology

- **TUI** — terminal UI (Phase 1, Textual). "GUI" is reserved for the browser-rendered app.
- **GUI** — browser-based graphical UI (Phase 2, FastAPI + web frontend).

---

## Goal

Build interactive interfaces for the `energy` CLI that present EIA datasets in their native tree/path hierarchy and support:

- Browsing the dataset tree
- Viewing schema and summary for a selected dataset
- Selecting multiple datasets for download
- Displaying download status in real time

The existing CLI (`energy inventory`, `energy download`, `energy schema`, `energy status`) is preserved alongside both interfaces.

## Approach: TUI first, browser GUI second

Start with a Textual terminal UI (local, Python-only, fast to build). When ready, add a FastAPI + web frontend deployable to GCP Cloud Run as a sibling app in the same repo.

The `eia/` package is the stable core — all business logic lives there and is shared by the CLI, TUI, and GUI. Only the UI layer and storage layer differ between phases.

---

## Full repo layout

Each interface layer (`tui/`, `web/`, `r/`) is a sibling that imports from `eia/`. None of them know about each other. `eia/` has no knowledge of any UI layer.

```
eia/                ← shared core (CLI, TUI, and GUI all import from here)
  client.py
  inventory.py
  downloader.py
  schema.py
  storage.py        ← storage abstraction (LocalStorage / GCSStorage)
  cli.py            ← CLI adapter

tui/                ← terminal UI — Phase 1
  __init__.py
  app.py
  screens/
    browser.py      ← dataset tree + schema panel
    download.py     ← download queue
  widgets/
    tree.py
    schema.py
    progress.py

web/                ← browser GUI — Phase 2
  api/              ← FastAPI backend
    main.py
    routers/
      inventory.py
      schema.py
      download.py
  frontend/         ← Vue or HTMX
    src/
  Dockerfile

r/                  ← R/Shiny analysis app (existing)

tests/
  test_inventory.py
  test_schema.py
  test_tui.py       ← added in Phase 1
  test_web.py       ← added in Phase 2

main.py             ← dev shim
pyproject.toml
```

`pyproject.toml` entry points and optional extras per layer:

```toml
[project.scripts]
energy     = "eia.cli:main"
energy-tui = "tui.app:main"

[project.optional-dependencies]
tui = ["textual>=1.0"]
web = ["fastapi>=0.100", "uvicorn>=0.23"]
dev = ["pytest>=8.0"]
```

```bash
pip install -e .           # CLI only
pip install -e ".[tui]"    # CLI + TUI
pip install -e ".[web]"    # CLI + browser GUI backend
```

Note on `eia/cli.py`: it is a UI adapter living inside the business logic package — a slight blurring of the boundary. Acceptable for now; it could move to a top-level `cli/` package later, but not worth the churn at this stage.

---

## Phase 1 — TUI (Textual, local)

### Why Textual

- Native `Tree` widget maps directly onto the EIA route hierarchy
- Real-time download progress bars built in
- Shares existing `eia/` modules with zero refactoring
- CLI stays intact alongside it
- No browser, no build tooling, no JavaScript

### Features

| Feature | Implementation |
|---------|---------------|
| Dataset tree | Textual `Tree` widget, lazily loaded via `eia/inventory.py` |
| Schema panel | Side panel populated by `eia/schema.py` on selection |
| Multi-select download | Checkbox nodes + download queue, progress per dataset |
| Download status | Textual `ProgressBar` per dataset, status in footer |

### Critical design decision — storage abstraction

The local `data/` path is currently hardcoded throughout `eia/downloader.py` and `eia/schema.py`. Before building Phase 1, introduce a thin `Storage` interface so Phase 2 is a config swap, not a code refactor.

```python
# eia/storage.py
class Storage(Protocol):
    def read(self, path: str) -> bytes: ...
    def write(self, path: str, data: bytes) -> None: ...
    def exists(self, path: str) -> bool: ...
    def list(self, prefix: str) -> list[str]: ...

class LocalStorage:
    """Current behavior — reads/writes data/ on local filesystem."""

class GCSStorage:
    """Phase 2 — reads/writes a GCS bucket."""
```

`downloader.py` and `schema.py` accept a `Storage` instance rather than constructing `Path` objects directly. The CLI and TUI pass `LocalStorage()`; the Cloud Run app passes `GCSStorage(bucket)`.

---

## Phase 2 — Browser GUI on GCP Cloud Run

### Architecture

```
Browser (Vue or HTMX)
        │  HTTP / SSE
FastAPI backend  (web/api/)
        │
   eia/ package          ←── unchanged from Phase 1
        │
  GCS bucket             ←── replaces local data/ directory
```

### Why Cloud Run

- Containerized (Docker), scales to zero — cheap for occasional use
- No infrastructure to manage
- Natural fit for a FastAPI service
- GCS provides durable, shared storage for downloaded Parquet files

### Migration steps from Phase 1

1. **Storage swap** — replace `LocalStorage` with `GCSStorage`; all `eia/` logic unchanged
2. **FastAPI backend** — thin HTTP layer in `web/api/` wrapping `eia/` functions
3. **Web frontend** — tree browser, schema panel, download queue in `web/frontend/`
4. **Containerize** — `web/Dockerfile` + Cloud Run deployment
5. **Auth** — GCP IAP or simple API key for access control

### FastAPI endpoint map

| Endpoint | Maps to |
|----------|---------|
| `GET /inventory?path=&depth=` | `eia/inventory.py` |
| `GET /schema/{path}` | `eia/schema.py` |
| `POST /download` | `eia/downloader.py` |
| `GET /download/status` (SSE) | live download progress stream |
| `GET /status` | `eia/downloader.status()` |

---

## What the CLI preserves

The CLI commands continue to work throughout both phases. In Phase 1 they use `LocalStorage`. In Phase 2 they can optionally target a GCS bucket via environment variable, keeping the CLI useful for scripting against the same data the browser app uses.

---

## Sequencing

```
Done        Storage abstraction (eia/storage.py)
Done        Phase 1 TUI (energy-tui command, tui/app.py)
Phase 2     Browser GUI — web/api/ + web/frontend/ + GCS + Cloud Run  ←── next
```
