"""
energy-tui — interactive terminal browser for EIA energy datasets.

Layout:
  Left:  dataset tree (lazy-loaded from EIA API, cached locally)
  Right: schema / summary panel for the selected dataset
  Bottom: download queue with progress bars

Keys:
  d         download selected dataset (adds to queue)
  r         refresh schema for selected dataset
  q / ctrl+c  quit
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import Footer, Header, Label, ProgressBar, Static, Tree
from textual.widgets.tree import TreeNode


# ── Domain types ─────────────────────────────────────────────────────────────

@dataclass
class RouteData:
    path: str
    name: str
    is_leaf: bool = False
    loaded: bool = False


@dataclass
class DownloadJob:
    path: str
    name: str
    total: int = 0
    done: int = 0
    status: str = "queued"  # queued | running | done | error
    error: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(v: int | float | None) -> str:
    if v is None:
        return "—"
    v = int(v)
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if abs(v) >= 10_000:
        return f"{v / 1_000:.0f}k"
    return f"{v:,}"


def _blocking_fetch_routes(path: str) -> list[dict]:
    """Run in a thread — returns list of {id, name, description, path, is_leaf}."""
    from eia.client import EIAClient
    from eia.inventory import _parse_routes
    client = EIAClient()
    data = client.get(path)
    routes = _parse_routes(data, path)
    return [
        {"id": r.id, "name": r.name, "description": r.description,
         "path": r.path, "is_leaf": r.is_leaf}
        for r in routes
    ]


def _blocking_load_schema(path: str, refresh: bool = False) -> dict:
    """Run in a thread — returns schema dict."""
    from eia.client import EIAClient, EIAError
    from eia.schema import load_or_fetch
    try:
        client = EIAClient()
    except EIAError:
        client = None
    return load_or_fetch(client, path, refresh=refresh)


def _blocking_download(path: str, progress_cb) -> int:
    """
    Run in a thread — downloads dataset, calls progress_cb(done, total) each page.
    Returns total rows downloaded.
    """
    import pandas as pd
    from datetime import datetime, timezone
    import json as _json

    from eia.client import EIAClient
    from eia.downloader import fetch_dataset_metadata, _load_catalog, _save_catalog, PAGE_SIZE
    from eia.schema import load_or_fetch
    from eia.storage import default_storage

    client = EIAClient()
    storage = default_storage()
    meta = fetch_dataset_metadata(client, path)

    freqs = meta.get("frequency", [])
    if not freqs:
        raise ValueError("No frequency information")
    frequency = freqs[0]["id"]
    data_cols = list(meta.get("data", {}).keys())
    if not data_cols:
        raise ValueError("No data columns")

    params: dict = {"frequency": frequency, "length": PAGE_SIZE}
    for col in data_cols:
        params.setdefault("data[]", []).append(col)

    probe = client.get(f"{path}/data", **{**params, "length": 1, "offset": 0})
    total = int(probe.get("total", 0))
    progress_cb(0, total)

    pages = []
    offset = 0
    while offset < total:
        page = client.get(f"{path}/data", **{**params, "offset": offset})
        rows = page.get("data", [])
        if not rows:
            break
        pages.append(pd.DataFrame(rows))
        offset += len(rows)
        progress_cb(offset, total)

    df = pd.concat(pages, ignore_index=True) if pages else pd.DataFrame()
    for col in data_cols:
        if col in df.columns:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() > 0:
                df[col] = converted

    storage.write_text(
        f"{path}/metadata.json",
        _json.dumps({
            "path": path,
            "name": meta.get("name", path),
            "description": meta.get("description", ""),
            "frequency": frequency,
            "data_columns": data_cols,
            "facets": meta.get("facets", []),
            "rows": len(df),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2)
    )
    df.to_parquet(storage.uri(f"{path}/data.parquet"), index=False)
    load_or_fetch(client=None, path=path, refresh=True, storage=storage)

    catalog = _load_catalog(storage)
    catalog[path] = {
        "name": meta.get("name", path),
        "rows": len(df),
        "frequency": frequency,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "schema_cached": True,
    }
    _save_catalog(catalog, storage)
    return len(df)


# ── Schema panel ─────────────────────────────────────────────────────────────

class SchemaPanel(ScrollableContainer):
    DEFAULT_CSS = """
    SchemaPanel {
        width: 1fr;
        border: solid $primary-darken-2;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[dim]Select a dataset in the tree.[/dim]", id="schema-content")

    def show_loading(self, path: str) -> None:
        self.query_one("#schema-content", Static).update(
            f"[dim]Loading schema for [bold]{path}[/bold]…[/dim]"
        )

    def show_hint(self, text: str) -> None:
        self.query_one("#schema-content", Static).update(f"[dim]{text}[/dim]")

    def show_schema(self, path: str, schema: dict) -> None:
        local = schema.get("local_stats", {})
        downloaded = bool(local)
        lines: list[str] = []

        lines.append(f"[bold cyan]{schema.get('name', path)}[/bold cyan]")
        lines.append(f"[dim]{path}[/dim]")

        if schema.get("description"):
            lines.append(f"\n[dim]{schema['description'][:200]}[/dim]")

        status = (
            "[green]downloaded[/green]" if downloaded
            else "[yellow]not downloaded — press [bold]d[/bold] to download[/yellow]"
        )
        lines.append(f"\nStatus: {status}")

        freqs = ", ".join(f["id"] for f in schema.get("frequencies", []))
        lines.append(f"[bold]Frequencies:[/bold] {freqs or '—'}")

        if downloaded and local.get("period_actual_start"):
            lines.append(
                f"[bold]Period:[/bold]      {local['period_actual_start']} → "
                f"{local['period_actual_end']}  ({local.get('rows', 0):,} rows)"
            )
        elif schema.get("period_start"):
            lines.append(
                f"[bold]Period:[/bold]      {schema['period_start']} → "
                f"{schema['period_end']}  [dim](from API)[/dim]"
            )

        if schema.get("columns"):
            lines.append("\n[bold]Data columns[/bold]")
            col_stats = local.get("column_stats", {})
            for col_id, col_meta in schema["columns"].items():
                units = col_meta.get("units", "") if isinstance(col_meta, dict) else ""
                s = col_stats.get(col_id)
                if s:
                    lines.append(
                        f"  [green]{col_id}[/green]  [dim]{units}[/dim]"
                        f"  min={_fmt(s['min'])} max={_fmt(s['max'])} mean={_fmt(s['mean'])}"
                    )
                else:
                    lines.append(f"  [green]{col_id}[/green]  [dim]{units}[/dim]")

        facet_stats = local.get("facet_stats", {})
        for facet in schema.get("facets", []):
            fid = facet.get("id", "")
            fdesc = facet.get("description", fid)
            fs = facet_stats.get(fid, {})
            count = fs.get("count")
            values = fs.get("values", [])
            count_str = f"  [dim]{count} unique[/dim]" if count else ""
            lines.append(f"\n[bold]{fdesc}[/bold] [dim]({fid})[/dim]{count_str}")
            for v in values[:20]:
                lines.append(f"  [dim]{v}[/dim]")
            if count and count > len(values):
                lines.append(f"  [dim]… and {count - len(values)} more[/dim]")

        self.query_one("#schema-content", Static).update("\n".join(lines))


# ── Download queue panel ──────────────────────────────────────────────────────

class DownloadQueue(ScrollableContainer):
    DEFAULT_CSS = """
    DownloadQueue {
        height: 8;
        border-top: solid $primary-darken-2;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._jobs: list[DownloadJob] = []

    def compose(self) -> ComposeResult:
        if not self._jobs:
            yield Label(
                "[dim]No downloads queued.  Select a dataset and press [bold]d[/bold].[/dim]",
                id="dq-empty"
            )
        for job in self._jobs:
            icon = {"queued": "○", "running": "↓", "done": "✓", "error": "✗"}.get(job.status, "?")
            color = {"queued": "dim", "running": "yellow", "done": "green", "error": "red"}.get(job.status, "")
            label = f"[{color}]{icon}  {job.name}[/{color}]"
            if job.status == "error":
                label += f"  [red dim]{job.error[:60]}[/red dim]"
            elif job.status == "running" and job.total:
                pct = int(100 * job.done / job.total)
                bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                label += f"  [dim]{bar} {pct}%[/dim]"
            yield Label(label, id=f"dq-{job.path.replace('/', '-')}")

    def _refresh_display(self) -> None:
        self.remove_children()
        self.mount(*list(self.compose()))

    def add_job(self, job: DownloadJob) -> None:
        self._jobs.append(job)
        self._refresh_display()

    def update_job(self, path: str, **kwargs) -> None:
        for j in self._jobs:
            if j.path == path:
                for k, v in kwargs.items():
                    setattr(j, k, v)
        self._refresh_display()

    def has_job(self, path: str) -> bool:
        return any(j.path == path for j in self._jobs)


# ── Main app ──────────────────────────────────────────────────────────────────

class EnergyTUI(App):
    TITLE = "energy-tui"
    SUB_TITLE = "EIA Open Data"

    CSS = """
    #tree-panel {
        width: 2fr;
        border: solid $primary-darken-2;
        padding: 1 1;
    }
    #main-row {
        height: 1fr;
    }
    Tree { background: $surface; }
    """

    BINDINGS = [
        Binding("d", "download", "Download"),
        Binding("r", "refresh_schema", "Refresh schema"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._selected_path: str | None = None
        self._selected_name: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(id="main-row"):
                with ScrollableContainer(id="tree-panel"):
                    tree: Tree[RouteData] = Tree("EIA Open Data", id="dataset-tree")
                    tree.root.data = RouteData(path="", name="EIA Open Data", loaded=False)
                    tree.root.expand()
                    yield tree
                yield SchemaPanel(id="schema-panel")
            yield DownloadQueue(id="download-queue")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._load_children(self.query_one("#dataset-tree", Tree).root, ""))

    # ── Tree loading ──────────────────────────────────────────────────────────

    async def _load_children(self, node: TreeNode[RouteData], path: str) -> None:
        try:
            routes = await asyncio.to_thread(_blocking_fetch_routes, path)
        except Exception as e:
            self.query_one("#schema-panel", SchemaPanel).show_hint(f"API error: {e}")
            return

        node.remove_children()
        for r in routes:
            node.add(
                f"[bold]{r['name']}[/bold]  [dim green]{r['path']}[/dim green]",
                data=RouteData(path=r["path"], name=r["name"]),
                allow_expand=True,
            )
        if node.data:
            node.data.loaded = True

    async def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        data: RouteData | None = node.data
        if data is None or data.loaded or not data.path:
            return
        data.loaded = True
        await self._expand_node(node, data.path)

    async def _expand_node(self, node: TreeNode[RouteData], path: str) -> None:
        try:
            routes = await asyncio.to_thread(_blocking_fetch_routes, path)
        except Exception:
            return

        node.remove_children()
        if not routes:
            # This is a data leaf — load schema automatically
            if node.data:
                node.data.is_leaf = True
            await self._show_schema(path)
            return

        for r in routes:
            node.add(
                f"[bold]{r['name']}[/bold]  [dim green]{r['path']}[/dim green]",
                data=RouteData(path=r["path"], name=r["name"]),
                allow_expand=True,
            )

    # ── Selection → schema ────────────────────────────────────────────────────

    async def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data: RouteData | None = event.node.data
        if data is None or not data.path:
            return
        self._selected_path = data.path
        self._selected_name = data.name
        self.run_worker(self._show_schema(data.path))

    async def _show_schema(self, path: str, refresh: bool = False) -> None:
        panel = self.query_one("#schema-panel", SchemaPanel)
        panel.show_loading(path)
        try:
            schema = await asyncio.to_thread(_blocking_load_schema, path, refresh)
            panel.show_schema(path, schema)
        except Exception as e:
            panel.show_hint(f"Could not load schema for {path}: {e}")

    # ── Download ──────────────────────────────────────────────────────────────

    def action_download(self) -> None:
        path = self._selected_path
        name = self._selected_name or path
        if not path:
            self.notify("Select a dataset first.", severity="warning")
            return
        queue = self.query_one("#download-queue", DownloadQueue)
        if queue.has_job(path):
            self.notify(f"Already queued: {path}", severity="warning")
            return
        job = DownloadJob(path=path, name=name or path)
        queue.add_job(job)
        self.notify(f"Queued: {name}")
        self.run_worker(self._run_download(path, name or path))

    async def _run_download(self, path: str, name: str) -> None:
        queue = self.query_one("#download-queue", DownloadQueue)
        queue.update_job(path, status="running")

        loop = asyncio.get_event_loop()

        def progress_cb(done: int, total: int) -> None:
            loop.call_soon_threadsafe(queue.update_job, path, done=done, total=total)

        try:
            rows = await asyncio.to_thread(_blocking_download, path, progress_cb)
            queue.update_job(path, status="done", done=rows, total=rows)
            self.notify(f"Downloaded {rows:,} rows — {name}")
            if self._selected_path == path:
                self.run_worker(self._show_schema(path))
        except Exception as e:
            queue.update_job(path, status="error", error=str(e))
            self.notify(f"Download failed: {e}", severity="error")

    # ── Refresh schema ────────────────────────────────────────────────────────

    def action_refresh_schema(self) -> None:
        path = self._selected_path
        if not path:
            self.notify("Select a dataset first.", severity="warning")
            return
        self.notify(f"Refreshing schema for {path}…")
        self.run_worker(self._show_schema(path, refresh=True))


def main() -> None:
    EnergyTUI().run()


if __name__ == "__main__":
    main()
