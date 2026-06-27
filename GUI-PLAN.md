# GUI Plan

## Goal

Build an interactive GUI for the `energy` CLI that presents EIA datasets in their native tree/path hierarchy and supports:

- Browsing the dataset tree
- Viewing schema and summary for a selected dataset
- Selecting multiple datasets for download
- Displaying download status in real time

The existing CLI (`energy inventory`, `energy download`, `energy schema`, `energy status`) is preserved alongside the GUI.

## Approach: Textual first, Cloud Run second

Start with a Textual terminal UI (local, Python-only, fast to build). When ready, migrate to a FastAPI + web frontend app deployable to GCP Cloud Run.

The `eia/` package is the stable core — all business logic lives there and carries over unchanged between phases. Only the UI layer and storage layer change.

---

## Phase 1 — Textual (local TUI)

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

### Code separation

`gui/` is a sibling package to `eia/`, not nested inside it. `eia/` has no knowledge of `gui/` — the dependency is strictly one-way: `gui/` imports from `eia/`, never the reverse.

```
eia/                ← core business logic (unchanged)
  client.py
  inventory.py
  downloader.py
  schema.py
  storage.py        ← storage abstraction (see below)
  cli.py            ← CLI adapter, stays here

gui/                ← TUI package
  __init__.py
  app.py            ← Textual app entry point
  screens/
    browser.py      ← dataset tree + schema panel
    download.py     ← download queue
  widgets/
    tree.py         ← EIA route tree widget
    schema.py       ← schema/summary display
    progress.py     ← per-dataset download progress

tests/
  test_inventory.py
  test_schema.py
  test_gui.py       ← TUI regression tests, added in Phase 1
```

`textual` is an optional dependency — installing the base package gives the CLI only:

```toml
[project.scripts]
energy     = "eia.cli:main"
energy-gui = "gui.app:main"

[project.optional-dependencies]
gui = ["textual>=1.0"]
dev = ["pytest>=8.0"]
```

```bash
pip install -e .          # CLI only
pip install -e ".[gui]"   # CLI + TUI
```

The note on `eia/cli.py`: it is a UI adapter living inside the business logic package, which is a slight blurring of the boundary. Acceptable for now; it could move to a top-level `cli/` package later if the project grows, but not worth the churn at this stage.

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

`downloader.py` and `schema.py` accept a `Storage` instance rather than constructing `Path` objects directly. The CLI and Textual app pass `LocalStorage()`; the Cloud Run app passes `GCSStorage(bucket)`.

---

## Phase 2 — Browser app on GCP Cloud Run

### Architecture

```
Browser (Vue or HTMX)
        │  HTTP / SSE
FastAPI backend
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
2. **FastAPI backend** — thin HTTP layer wrapping `eia/` functions; one endpoint per CLI command
3. **Web frontend** — tree browser, schema panel, download queue; replaces Textual UI
4. **Containerize** — `Dockerfile` + Cloud Run deployment
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

The CLI commands (`energy inventory`, `energy download`, `energy schema`, `energy status`) continue to work throughout both phases. In Phase 1 they use `LocalStorage`. In Phase 2 they can optionally be pointed at a GCS bucket via an environment variable, so the CLI remains useful for scripting against the same data the web app uses.

---

## Sequencing

```
Now         Introduce Storage abstraction, refactor downloader + schema to use it
Phase 1     Build Textual GUI (energy-gui command)
Phase 2     FastAPI backend + web frontend + GCS + Cloud Run deployment
```
