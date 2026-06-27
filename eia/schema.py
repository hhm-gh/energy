"""
Schema and summary for EIA datasets.

For any dataset path:
  - API metadata (name, facets, columns, frequencies) is fetched once and
    cached to {storage}/{path}/schema.json — no data download required.
  - If the dataset has been downloaded, computed stats (value ranges, unique
    facet values, period span) are added to schema.json from the local Parquet.

Neither layer re-hits the API once cached, unless --refresh is passed.
"""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table
from rich import box

from .client import EIAClient
from .storage import Storage, default_storage

console = Console()


# ── Fetch and cache ───────────────────────────────────────────────────────────

def _fetch_api_schema(client: EIAClient, path: str) -> dict:
    """One API call — returns route metadata without downloading data."""
    meta = client.get(path)
    return {
        "name":         meta.get("name", path),
        "description":  meta.get("description", ""),
        "frequencies":  meta.get("frequency", []),
        "facets":       meta.get("facets", []),
        "columns":      meta.get("data", {}),
        "period_start": meta.get("startPeriod"),
        "period_end":   meta.get("endPeriod"),
    }


def _compute_local_stats(path: str, schema: dict, storage: Storage) -> dict:
    """Enrich schema with stats computed from the local Parquet — no API call."""
    import pandas as pd

    df = pd.read_parquet(storage.uri(f"{path}/data.parquet"))
    stats: dict = {}

    # Period span
    if "period" in df.columns:
        stats["period_actual_start"] = str(df["period"].min())
        stats["period_actual_end"]   = str(df["period"].max())

    stats["rows"] = len(df)

    # Numeric column ranges
    col_stats = {}
    for col in schema.get("columns", {}):
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            s = df[col].dropna()
            nz = s[s > 0]
            if len(s):
                col_stats[col] = {
                    "min":    round(float(s.min())),
                    "max":    round(float(s.max())),
                    "mean":   round(float(s.mean())),
                    "median": round(float(s.median())),
                    "min_nz":  round(float(nz.min())) if len(nz) else None,
                    "mean_nz": round(float(nz.mean())) if len(nz) else None,
                }
    stats["column_stats"] = col_stats

    # Unique values per facet (list if ≤30, count only if more)
    facet_stats = {}
    for facet in schema.get("facets", []):
        col = facet.get("id")
        # EIA description columns follow no single pattern — try common variants
        root = col[:-2] if col and col.endswith("id") else col
        desc_col = next(
            (c for c in (root + "Description", root + "Name", col + "Description")
             if c in df.columns),
            None,
        )
        if col and col in df.columns:
            unique_ids = sorted(df[col].dropna().unique().tolist())
            if desc_col:
                pairs = (df[[col, desc_col]].drop_duplicates()
                         .sort_values(col)
                         .apply(lambda r: f"{r[col]} — {r[desc_col]}", axis=1)
                         .tolist())
                facet_stats[col] = {"count": len(pairs),
                                    "values": pairs if len(pairs) <= 30 else pairs[:30]}
            else:
                facet_stats[col] = {"count": len(unique_ids),
                                    "values": unique_ids if len(unique_ids) <= 30 else unique_ids[:30]}
    stats["facet_stats"] = facet_stats

    return stats


def load_or_fetch(
    client: EIAClient | None,
    path: str,
    refresh: bool = False,
    storage: Storage | None = None,
) -> dict:
    """
    Return the schema dict for a dataset path.
    Reads from cache if available; fetches from API (requires client) if not.
    Enriches with local stats if Parquet is present.
    """
    if storage is None:
        storage = default_storage()

    schema_key = f"{path}/schema.json"
    parquet_present = storage.exists(f"{path}/data.parquet")

    # Load cached schema
    if storage.exists(schema_key) and not refresh:
        schema = json.loads(storage.read_text(schema_key))
    else:
        if client is None:
            raise ValueError(f"No cached schema for '{path}'. Provide an API client to fetch it.")
        schema = _fetch_api_schema(client, path)

    # Enrich with local stats if data is present
    if parquet_present and ("rows" not in schema.get("local_stats", {}) or refresh):
        schema["local_stats"] = _compute_local_stats(path, schema, storage)

    # Persist
    storage.write_text(schema_key, json.dumps(schema, indent=2))

    return schema


# ── Path listing ──────────────────────────────────────────────────────────────

def print_paths(storage: Storage | None = None) -> None:
    """List all paths with a locally cached schema, grouped by download status."""
    if storage is None:
        storage = default_storage()

    schema_keys = storage.find("schema.json")

    if not schema_keys:
        console.print("[dim]No local data yet. Run: energy download <path>[/dim]")
        console.print("[dim]To see all available paths: energy inventory --flat[/dim]")
        return

    entries = []
    for schema_key in schema_keys:
        # key is like "electricity/retail-sales/schema.json"
        path = schema_key.removesuffix("/schema.json")
        parquet_present = storage.exists(f"{path}/data.parquet")
        try:
            meta = json.loads(storage.read_text(schema_key))
            name = meta.get("name", path)
            freqs = ", ".join(f["id"] for f in meta.get("frequencies", []))
            local = meta.get("local_stats", {})
            rows = f"{local['rows']:,}" if local.get("rows") else "—"
        except Exception:
            name, freqs, rows = path, "—", "—"

        entries.append((parquet_present, path, name, freqs, rows))

    if not entries:
        console.print("[dim]No cached schemas yet.[/dim]")
        console.print("[dim]Run: energy schema <path>  or  energy download <path>[/dim]")
        console.print("[dim]To see all available paths: energy inventory --flat[/dim]")
        return

    console.print("\n[bold]Known dataset paths[/bold]  "
                  "[dim]● downloaded   ○ schema cached (not downloaded)[/dim]\n")
    for downloaded, path, name, freqs, rows in entries:
        marker = "[green]●[/green]" if downloaded else "[yellow]○[/yellow]"
        detail_parts = []
        if freqs:
            detail_parts.append(freqs)
        if rows != "—":
            detail_parts.append(f"{rows} rows")
        detail = "   [dim]" + "   ".join(detail_parts) + "[/dim]" if detail_parts else ""
        console.print(f"  {marker} [bold green]{path}[/bold green]   {name}{detail}",
                      no_wrap=True, overflow="ellipsis")

    console.print("\n[dim]For all EIA routes: energy inventory --flat[/dim]")


# ── Display ───────────────────────────────────────────────────────────────────

def print_schema(path: str, schema: dict) -> None:
    local = schema.get("local_stats", {})
    downloaded = bool(local)

    # Header
    console.print(f"\n[bold cyan]{schema['name']}[/bold cyan]  [dim]{path}[/dim]")
    if schema.get("description"):
        console.print(f"[dim]{schema['description'][:200]}[/dim]")

    status = "[green]downloaded[/green]" if downloaded else "[yellow]not downloaded[/yellow]"
    console.print(f"Status: {status}\n")

    # Frequencies
    freqs = ", ".join(f["id"] for f in schema.get("frequencies", []))
    console.print(f"[bold]Frequencies:[/bold] {freqs or '—'}")

    # Period
    if downloaded and local.get("period_actual_start"):
        console.print(f"[bold]Period:[/bold]      {local['period_actual_start']} → {local['period_actual_end']}  "
                      f"({local.get('rows', 0):,} rows)")
    elif schema.get("period_start"):
        console.print(f"[bold]Period:[/bold]      {schema['period_start']} → {schema['period_end']}  [dim](from API)[/dim]")

    # Data columns
    console.print()

    def _fmt(v: int | None) -> str:
        if v is None:
            return "—"
        if abs(v) >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if abs(v) >= 10_000:
            return f"{v / 1_000:.0f}k"
        return f"{v:,}"

    col_table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    col_table.add_column("Column", no_wrap=True, min_width=10)
    col_table.add_column("Units", no_wrap=True)
    col_table.add_column("Min", justify="right")
    col_table.add_column("Max", justify="right")
    col_table.add_column("Mean", justify="right")
    col_table.add_column("Min (>0)", justify="right")
    col_table.add_column("Mean (>0)", justify="right")
    col_stats = local.get("column_stats", {})
    for col_id, col_meta in schema.get("columns", {}).items():
        units = col_meta.get("units", "—") if isinstance(col_meta, dict) else "—"
        if col_id in col_stats:
            s = col_stats[col_id]
            col_table.add_row(
                col_id, units,
                _fmt(s["min"]), _fmt(s["max"]), _fmt(s["mean"]),
                _fmt(s["min_nz"]), _fmt(s["mean_nz"]),
            )
        else:
            col_table.add_row(col_id, units, "—", "—", "—", "—", "—")
    console.print(col_table)

    # Facets
    facet_stats = local.get("facet_stats", {})
    for facet in schema.get("facets", []):
        fid = facet.get("id", "")
        fdesc = facet.get("description", fid)
        fs = facet_stats.get(fid, {})
        count = fs.get("count")
        values = fs.get("values", [])

        header = f"[bold]{fdesc}[/bold] [dim]({fid})[/dim]"
        if count is not None:
            header += f"  [dim]{count} unique[/dim]"
        console.print(header)

        if values:
            col_width = 36
            cols = max(1, console.width // col_width)
            for i in range(0, len(values), cols):
                row = values[i:i + cols]
                console.print("  " + "   ".join(f"[dim]{v}[/dim]".ljust(col_width) for v in row))
            if count and count > len(values):
                console.print(f"  [dim]… and {count - len(values)} more[/dim]")
        console.print()
