"""
Schema and summary for EIA datasets.

For any dataset path:
  - API metadata (name, facets, columns, frequencies) is fetched once and
    cached to data/{path}/schema.json — no data download required.
  - If the dataset has been downloaded, computed stats (value ranges, unique
    facet values, period span) are added to schema.json from the local Parquet.

Neither layer re-hits the API once cached, unless --refresh is passed.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

from .client import EIAClient

DATA_ROOT = Path("data")
console = Console()


def _schema_path(path: str) -> Path:
    return DATA_ROOT / path / "schema.json"


def _parquet_path(path: str) -> Path:
    return DATA_ROOT / path / "data.parquet"


def _metadata_path(path: str) -> Path:
    return DATA_ROOT / path / "metadata.json"


# ── Fetch and cache ───────────────────────────────────────────────────────────

def _fetch_api_schema(client: EIAClient, path: str) -> dict:
    """One API call — returns route metadata without downloading data."""
    meta = client.get(path)
    return {
        "name":        meta.get("name", path),
        "description": meta.get("description", ""),
        "frequencies": meta.get("frequency", []),
        "facets":      meta.get("facets", []),
        "columns":     meta.get("data", {}),
        "period_start": meta.get("startPeriod"),
        "period_end":   meta.get("endPeriod"),
    }


def _compute_local_stats(path: str, schema: dict) -> dict:
    """Enrich schema with stats computed from the local Parquet — no API call."""
    import pandas as pd

    df = pd.read_parquet(_parquet_path(path))
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
            if len(s):
                col_stats[col] = {
                    "min":    round(float(s.min()), 4),
                    "max":    round(float(s.max()), 4),
                    "mean":   round(float(s.mean()), 4),
                    "median": round(float(s.median()), 4),
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


def load_or_fetch(client: EIAClient | None, path: str, refresh: bool = False) -> dict:
    """
    Return the schema dict for a dataset path.
    Reads from cache if available; fetches from API (requires client) if not.
    Enriches with local stats if Parquet is present.
    """
    schema_file = _schema_path(path)
    parquet_present = _parquet_path(path).exists()

    # Load cached schema
    if schema_file.exists() and not refresh:
        schema = json.loads(schema_file.read_text())
    else:
        if client is None:
            raise ValueError(f"No cached schema for '{path}'. Provide an API client to fetch it.")
        schema = _fetch_api_schema(client, path)

    # Enrich with local stats if data is present
    if parquet_present and ("rows" not in schema or refresh):
        schema["local_stats"] = _compute_local_stats(path, schema)

    # Persist
    schema_file.parent.mkdir(parents=True, exist_ok=True)
    schema_file.write_text(json.dumps(schema, indent=2))

    return schema


# ── Path listing ─────────────────────────────────────────────────────────────

def print_paths() -> None:
    """List all paths with a locally cached schema, grouped by download status."""
    if not DATA_ROOT.exists():
        console.print("[dim]No local data yet. Run: energy download <path>[/dim]")
        console.print("[dim]To see all available paths: energy inventory --flat[/dim]")
        return

    # Collect every schema.json found under data/
    entries = []
    for schema_file in sorted(DATA_ROOT.rglob("schema.json")):
        rel = schema_file.parent.relative_to(DATA_ROOT)
        path = str(rel)
        parquet = (schema_file.parent / "data.parquet").exists()
        try:
            meta = json.loads(schema_file.read_text())
            name = meta.get("name", path)
            freqs = ", ".join(f["id"] for f in meta.get("frequencies", []))
            local = meta.get("local_stats", {})
            rows = f"{local['rows']:,}" if local.get("rows") else "—"
            period = (
                f"{local['period_actual_start']} → {local['period_actual_end']}"
                if local.get("period_actual_start") else
                f"{meta.get('period_start', '')} → {meta.get('period_end', '')} [dim](API)[/dim]"
                if meta.get("period_start") else "—"
            )
        except Exception:
            name, freqs, rows, period = path, "—", "—", "—"

        entries.append((parquet, path, name, freqs, rows, period))

    if not entries:
        console.print("[dim]No cached schemas yet.[/dim]")
        console.print("[dim]Run: energy schema <path>  or  energy download <path>[/dim]")
        console.print("[dim]To see all available paths: energy inventory --flat[/dim]")
        return

    console.print("\n[bold]Known dataset paths[/bold]  "
                  "[dim]● downloaded   ○ schema cached (not downloaded)[/dim]\n")
    for downloaded, path, name, freqs, rows, period in entries:
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
    col_table = Table("Column", "Units", "Min", "Max", "Mean",
                      box=box.SIMPLE, show_header=True, header_style="bold")
    col_stats = local.get("column_stats", {})
    for col_id, col_meta in schema.get("columns", {}).items():
        units = col_meta.get("units", "—") if isinstance(col_meta, dict) else "—"
        if col_id in col_stats:
            s = col_stats[col_id]
            col_table.add_row(col_id, units,
                              str(s["min"]), str(s["max"]), str(s["mean"]))
        else:
            col_table.add_row(col_id, units, "—", "—", "—")
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
            # Print in columns
            col_width = 36
            cols = max(1, console.width // col_width)
            for i in range(0, len(values), cols):
                row = values[i:i + cols]
                console.print("  " + "   ".join(f"[dim]{v}[/dim]".ljust(col_width) for v in row))
            if count and count > len(values):
                console.print(f"  [dim]… and {count - len(values)} more[/dim]")
        console.print()
