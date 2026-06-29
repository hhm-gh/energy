"""
energy-tui — interactive terminal browser for EIA energy datasets.

Tabs:
  API   — live EIA v2 API dataset tree (lazy-loaded, requires API key)
  Bulk  — local bulk dataset browser (reads from data/bulk/, no API key needed)

Keys (API tab):
  d         download selected dataset
  r         refresh schema for selected dataset
  q / ctrl+c  quit
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import Footer, Header, Label, Static, TabbedContent, TabPane, Tree
from textual.widgets.tree import TreeNode


# ── Domain types ──────────────────────────────────────────────────────────────

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


@dataclass
class BulkNodeData:
    kind: str        # "root" | "dataset" | "category" | "series"
    dataset_id: str
    node_id: str     # category_id or series_id; equals dataset_id for dataset nodes
    name: str
    loaded: bool = False


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
    from eia.client import EIAClient, EIAError
    from eia.schema import load_or_fetch
    try:
        client = EIAClient()
    except EIAError:
        client = None
    return load_or_fetch(client, path, refresh=refresh)


def _blocking_download(path: str, progress_cb) -> int:
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

    pages, offset = [], 0
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

    storage.write_text(f"{path}/metadata.json", _json.dumps({
        "path": path, "name": meta.get("name", path), "description": meta.get("description", ""),
        "frequency": frequency, "data_columns": data_cols, "facets": meta.get("facets", []),
        "rows": len(df), "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    df.to_parquet(storage.uri(f"{path}/data.parquet"), index=False)
    load_or_fetch(client=None, path=path, refresh=True, storage=storage)

    catalog = _load_catalog(storage)
    catalog[path] = {
        "name": meta.get("name", path), "rows": len(df), "frequency": frequency,
        "downloaded_at": datetime.now(timezone.utc).isoformat(), "schema_cached": True,
    }
    _save_catalog(catalog, storage)
    return len(df)


def _blocking_load_bulk_catalog() -> dict:
    p = Path("data/bulk_catalog.json")
    return json.loads(p.read_text()) if p.exists() else {}


def _blocking_load_bulk_dataset(dataset_id: str) -> dict:
    """Load categories and series_meta for a bulk dataset into an in-memory tree dict."""
    import pandas as pd

    base = Path(f"data/bulk/{dataset_id}")
    cats_df = pd.read_parquet(base / "categories.parquet")
    cat_ser_df = pd.read_parquet(base / "category_series.parquet")
    meta_df = pd.read_parquet(base / "series_meta.parquet")

    tree: dict[str, dict] = {}
    for row in cats_df.itertuples():
        parent = row.parent_category_id if (
            row.parent_category_id and pd.notna(row.parent_category_id)
        ) else None
        tree[row.category_id] = {
            "name": row.name, "parent": parent, "children": [], "series": [],
        }

    for cid, node in tree.items():
        parent = node["parent"]
        if parent and parent in tree and cid not in tree[parent]["children"]:
            tree[parent]["children"].append(cid)

    for row in cat_ser_df.itertuples():
        if row.category_id in tree:
            tree[row.category_id]["series"].append(row.series_id)

    roots = [
        cid for cid, node in tree.items()
        if not node["parent"] or node["parent"] not in tree
    ]

    series_meta: dict[str, dict] = {
        row.series_id: {
            "name": row.name, "units": row.units, "f": row.f,
            "geography": row.geography, "start": row.start, "end": row.end,
        }
        for row in meta_df.itertuples()
    }

    return {"tree": tree, "roots": roots, "series_meta": series_meta}


# ── Schema panel (API tab) ────────────────────────────────────────────────────

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


# ── Download queue panel (API tab) ────────────────────────────────────────────

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
                id="dq-empty",
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


# ── Bulk detail panel ─────────────────────────────────────────────────────────

class BulkDetailPanel(ScrollableContainer):
    DEFAULT_CSS = """
    BulkDetailPanel {
        width: 1fr;
        border: solid $primary-darken-2;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[dim]Select a dataset, category, or series in the tree.[/dim]",
            id="bulk-detail-content",
        )

    def _set(self, text: str) -> None:
        self.query_one("#bulk-detail-content", Static).update(text)

    def show_hint(self, text: str) -> None:
        self._set(f"[dim]{text}[/dim]")

    def show_dataset(self, dataset_id: str, info: dict) -> None:
        lines = [
            f"[bold cyan]{info.get('name', dataset_id)}[/bold cyan]",
            f"[dim]{dataset_id}[/dim]",
            "",
            f"[bold]Temporal:[/bold]    {info.get('temporal', '—')}",
            f"[bold]Downloaded:[/bold]  {info.get('downloaded_at', '')[:10]}",
            f"[bold]Raw size:[/bold]    {info.get('raw_size_mb', 0):.1f} MB"
            f"  ({info.get('line_count', 0):,} records)",
        ]
        if info.get("parsed"):
            lines += [
                f"[bold]Series:[/bold]      {info.get('series_count', 0):,}",
                f"[bold]Categories:[/bold]  {info.get('category_count', 0):,}",
                "",
                "[green]Parsed — expand to browse categories[/green]",
            ]
        else:
            lines += [
                "",
                "[yellow]Not parsed.[/yellow]",
                f"[dim]Run: energy bulk-parse {dataset_id}[/dim]",
            ]
        self._set("\n".join(lines))

    def show_category(self, name: str, category_id: str, node: dict) -> None:
        n_children = len(node.get("children", []))
        n_series = len(node.get("series", []))
        lines = [
            f"[bold cyan]{name}[/bold cyan]",
            f"[dim]category  {category_id}[/dim]",
        ]
        if n_children:
            lines += ["", f"[bold]Subcategories:[/bold]  {n_children}"]
        if n_series:
            lines += ["", f"[bold]Series:[/bold]  {n_series:,}"]
        self._set("\n".join(lines))

    def show_series(self, series_id: str, meta: dict) -> None:
        _freq = {"A": "annual", "Q": "quarterly", "M": "monthly",
                 "W": "weekly", "D": "daily", "H": "hourly"}
        f = meta.get("f", "")
        freq_str = f"{f} — {_freq.get(f, f)}" if f else "—"
        lines = [
            f"[bold cyan]{meta.get('name', series_id)}[/bold cyan]",
            f"[dim]{series_id}[/dim]",
            "",
            f"[bold]Units:[/bold]      {meta.get('units', '—')}",
            f"[bold]Frequency:[/bold]  {freq_str}",
            f"[bold]Geography:[/bold]  {meta.get('geography', '—')}",
            f"[bold]Period:[/bold]     {meta.get('start', '—')} → {meta.get('end', '—')}",
        ]
        self._set("\n".join(lines))


# ── API tab ───────────────────────────────────────────────────────────────────

class ApiTab(Widget):
    DEFAULT_CSS = """
    ApiTab {
        height: 1fr;
    }
    ApiTab #api-tree-panel {
        width: 2fr;
        border: solid $primary-darken-2;
        padding: 1 1;
    }
    ApiTab #api-main-row {
        height: 1fr;
    }
    ApiTab Tree { background: $surface; }
    """

    BINDINGS = [
        Binding("d", "download", "Download"),
        Binding("r", "refresh_schema", "Refresh schema"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected_path: str | None = None
        self._selected_name: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="api-main-row"):
                with ScrollableContainer(id="api-tree-panel"):
                    tree: Tree[RouteData] = Tree("EIA Open Data", id="api-dataset-tree")
                    tree.root.data = RouteData(path="", name="EIA Open Data", loaded=False)
                    tree.root.expand()
                    yield tree
                yield SchemaPanel(id="api-schema-panel")
            yield DownloadQueue(id="download-queue")

    def on_mount(self) -> None:
        self.run_worker(
            self._load_children(self.query_one("#api-dataset-tree", Tree).root, "")
        )

    # ── Tree loading ──────────────────────────────────────────────────────────

    async def _load_children(self, node: TreeNode[RouteData], path: str) -> None:
        try:
            routes = await asyncio.to_thread(_blocking_fetch_routes, path)
        except Exception as e:
            self.query_one("#api-schema-panel", SchemaPanel).show_hint(f"API error: {e}")
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
        panel = self.query_one("#api-schema-panel", SchemaPanel)
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
            self.app.notify("Select a dataset first.", severity="warning")
            return
        queue = self.query_one("#download-queue", DownloadQueue)
        if queue.has_job(path):
            self.app.notify(f"Already queued: {path}", severity="warning")
            return
        job = DownloadJob(path=path, name=name or path)
        queue.add_job(job)
        self.app.notify(f"Queued: {name}")
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
            self.app.notify(f"Downloaded {rows:,} rows — {name}")
            if self._selected_path == path:
                self.run_worker(self._show_schema(path))
        except Exception as e:
            queue.update_job(path, status="error", error=str(e))
            self.app.notify(f"Download failed: {e}", severity="error")

    # ── Refresh schema ────────────────────────────────────────────────────────

    def action_refresh_schema(self) -> None:
        path = self._selected_path
        if not path:
            self.app.notify("Select a dataset first.", severity="warning")
            return
        self.app.notify(f"Refreshing schema for {path}…")
        self.run_worker(self._show_schema(path, refresh=True))


# ── Bulk tab ──────────────────────────────────────────────────────────────────

class BulkTab(Widget):
    DEFAULT_CSS = """
    BulkTab {
        height: 1fr;
    }
    BulkTab #bulk-tree-panel {
        width: 2fr;
        border: solid $primary-darken-2;
        padding: 1 1;
    }
    BulkTab Tree { background: $surface; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._catalog: dict = {}
        self._dataset_data: dict[str, dict] = {}

    def compose(self) -> ComposeResult:
        with Horizontal():
            with ScrollableContainer(id="bulk-tree-panel"):
                tree: Tree[BulkNodeData] = Tree("Bulk Datasets", id="bulk-tree")
                tree.root.data = BulkNodeData(
                    kind="root", dataset_id="", node_id="", name="Bulk Datasets", loaded=True,
                )
                tree.root.expand()
                yield tree
            yield BulkDetailPanel(id="bulk-detail-panel")

    def on_mount(self) -> None:
        self.run_worker(self._load_catalog())

    async def _load_catalog(self) -> None:
        tree = self.query_one("#bulk-tree", Tree)
        panel = self.query_one("#bulk-detail-panel", BulkDetailPanel)
        try:
            catalog = await asyncio.to_thread(_blocking_load_bulk_catalog)
        except Exception as e:
            panel.show_hint(f"Error loading bulk catalog: {e}")
            return

        self._catalog = catalog
        tree.root.remove_children()

        if not catalog:
            tree.root.add_leaf(
                "[dim]No bulk datasets downloaded. Run: energy bulk-download <ID>[/dim]",
                data=BulkNodeData(kind="root", dataset_id="", node_id="", name=""),
            )
            tree.focus()
            return

        for did, info in sorted(catalog.items()):
            name = info.get("name", did)
            parsed = info.get("parsed", False)
            label = f"[bold]{did}[/bold]  [dim]{name}[/dim]"
            if not parsed:
                label += "  [dim yellow](not parsed)[/dim yellow]"
            if parsed:
                tree.root.add(
                    label,
                    data=BulkNodeData(kind="dataset", dataset_id=did, node_id=did, name=name),
                    allow_expand=True,
                )
            else:
                tree.root.add_leaf(
                    label,
                    data=BulkNodeData(kind="dataset", dataset_id=did, node_id=did, name=name),
                )
        tree.focus()

    # ── Tree events ───────────────────────────────────────────────────────────

    async def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        data: BulkNodeData | None = node.data
        if data is None or data.loaded or data.kind == "root":
            return
        data.loaded = True

        if data.kind == "dataset":
            await self._expand_dataset(node, data.dataset_id)
        elif data.kind == "category":
            self._expand_category(node, data.dataset_id, data.node_id)

    async def _expand_dataset(self, node: TreeNode[BulkNodeData], dataset_id: str) -> None:
        if dataset_id not in self._dataset_data:
            try:
                loaded = await asyncio.to_thread(_blocking_load_bulk_dataset, dataset_id)
                self._dataset_data[dataset_id] = loaded
            except Exception as e:
                node.add_leaf(
                    f"[red]Error loading {dataset_id}: {e}[/red]",
                    data=BulkNodeData(kind="root", dataset_id=dataset_id, node_id="", name=""),
                )
                return

        cat_tree = self._dataset_data[dataset_id]["tree"]
        roots = self._dataset_data[dataset_id]["roots"]
        node.remove_children()

        for cid in sorted(roots, key=lambda c: cat_tree[c]["name"]):
            cat = cat_tree[cid]
            has_children = bool(cat["children"] or cat["series"])
            node.add(
                f"[cyan]{cat['name']}[/cyan]  [dim]{cid}[/dim]",
                data=BulkNodeData(kind="category", dataset_id=dataset_id, node_id=cid, name=cat["name"]),
                allow_expand=has_children,
            )

    def _expand_category(
        self, node: TreeNode[BulkNodeData], dataset_id: str, category_id: str
    ) -> None:
        dataset_info = self._dataset_data.get(dataset_id, {})
        cat_tree = dataset_info.get("tree", {})
        series_meta = dataset_info.get("series_meta", {})
        cat = cat_tree.get(category_id, {})

        node.remove_children()

        for cid in sorted(cat.get("children", []), key=lambda c: cat_tree.get(c, {}).get("name", "")):
            child = cat_tree.get(cid, {})
            has_children = bool(child.get("children") or child.get("series"))
            node.add(
                f"[cyan]{child.get('name', cid)}[/cyan]  [dim]{cid}[/dim]",
                data=BulkNodeData(
                    kind="category", dataset_id=dataset_id, node_id=cid, name=child.get("name", cid)
                ),
                allow_expand=has_children,
            )

        for sid in sorted(cat.get("series", [])):
            meta = series_meta.get(sid, {})
            name = meta.get("name", "")
            label = f"[green]{sid}[/green]"
            if name:
                label += f"  [dim]{name[:60]}{'…' if len(name) > 60 else ''}[/dim]"
            node.add_leaf(
                label,
                data=BulkNodeData(kind="series", dataset_id=dataset_id, node_id=sid, name=name or sid),
            )

    # ── Selection → detail ────────────────────────────────────────────────────

    async def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data: BulkNodeData | None = event.node.data
        if data is None or data.kind == "root":
            return
        panel = self.query_one("#bulk-detail-panel", BulkDetailPanel)

        if data.kind == "dataset":
            panel.show_dataset(data.dataset_id, self._catalog.get(data.dataset_id, {}))
        elif data.kind == "category":
            cat = self._dataset_data.get(data.dataset_id, {}).get("tree", {}).get(data.node_id, {})
            panel.show_category(data.name, data.node_id, cat)
        elif data.kind == "series":
            meta = (
                self._dataset_data.get(data.dataset_id, {})
                .get("series_meta", {})
                .get(data.node_id, {})
            )
            panel.show_series(data.node_id, meta)


# ── Main app ──────────────────────────────────────────────────────────────────

class EnergyTUI(App):
    TITLE = "energy-tui"
    SUB_TITLE = "EIA Open Data"

    CSS = """
    TabbedContent { height: 1fr; }
    TabPane { padding: 0; height: 1fr; }
    """

    BINDINGS = [
        Binding("1", "switch_tab('tab-api')", "API tab"),
        Binding("2", "switch_tab('tab-bulk')", "Bulk tab"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            with TabPane("API", id="tab-api"):
                yield ApiTab()
            with TabPane("Bulk", id="tab-bulk"):
                yield BulkTab()
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab_id
        tree_id = "#api-dataset-tree" if tab_id == "tab-api" else "#bulk-tree"
        self.set_timer(0.05, lambda: self.query_one(tree_id, Tree).focus())


def main() -> None:
    EnergyTUI().run()


if __name__ == "__main__":
    main()
