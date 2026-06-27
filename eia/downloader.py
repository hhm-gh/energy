"""
Download EIA datasets to local Parquet files.

Layout:
  data/<api-path>/data.parquet
  data/<api-path>/metadata.json
  data/catalog.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn

from .client import EIAClient
from .storage import Storage, default_storage

PAGE_SIZE = 5000
CATALOG_KEY = "catalog.json"

console = Console()


def _load_catalog(storage: Storage) -> dict:
    if storage.exists(CATALOG_KEY):
        return json.loads(storage.read_text(CATALOG_KEY))
    return {}


def _save_catalog(catalog: dict, storage: Storage) -> None:
    storage.write_text(CATALOG_KEY, json.dumps(catalog, indent=2))


def fetch_dataset_metadata(client: EIAClient, path: str) -> dict:
    """Return the route metadata (frequencies, facets, available data columns)."""
    return client.get(path)


def download(
    client: EIAClient,
    path: str,
    frequency: str | None = None,
    storage: Storage | None = None,
) -> str:
    """
    Download all records for a dataset and save as Parquet.
    Returns the storage URI of the saved Parquet file.
    """
    if storage is None:
        storage = default_storage()

    meta = fetch_dataset_metadata(client, path)

    # Pick frequency: use provided, else first available
    freqs = meta.get("frequency", [])
    if not freqs:
        raise ValueError(f"No frequency information for {path}")
    if frequency:
        if not any(f["id"] == frequency for f in freqs):
            valid = [f["id"] for f in freqs]
            raise ValueError(f"Invalid frequency '{frequency}'. Valid options: {valid}")
    else:
        frequency = freqs[0]["id"]

    # All available data columns
    data_cols = list(meta.get("data", {}).keys())
    if not data_cols:
        raise ValueError(f"No data columns found for {path}")

    # Build base params — frequency param takes the id string directly
    params: dict = {"frequency": frequency, "length": PAGE_SIZE}
    for col in data_cols:
        params.setdefault("data[]", []).append(col)

    # Count total rows first
    probe = client.get(f"{path}/data", **{**params, "length": 1, "offset": 0})
    total = int(probe.get("total", 0))

    parquet_key = f"{path}/data.parquet"

    if total == 0:
        console.print(f"[yellow]No data returned for {path}[/yellow]")
        return storage.uri(parquet_key)

    console.print(f"Downloading [bold]{meta.get('name', path)}[/bold] — {total:,} rows")

    pages = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching", total=total)
        offset = 0
        while offset < total:
            page = client.get(f"{path}/data", **{**params, "offset": offset})
            rows = page.get("data", [])
            if not rows:
                break
            pages.append(pd.DataFrame(rows))
            offset += len(rows)
            progress.update(task, advance=len(rows))

    df = pd.concat(pages, ignore_index=True)

    # Coerce data columns to numeric where possible; leave strings as-is
    for col in data_cols:
        if col in df.columns:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() > 0:
                df[col] = converted

    df.to_parquet(storage.uri(parquet_key), index=False)

    # Save metadata alongside data
    meta_snapshot = {
        "path": path,
        "name": meta.get("name", path),
        "description": meta.get("description", ""),
        "frequency": frequency,
        "data_columns": data_cols,
        "facets": meta.get("facets", []),
        "rows": len(df),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    storage.write_text(f"{path}/metadata.json", json.dumps(meta_snapshot, indent=2))

    # Build and cache schema (API metadata + computed local stats) in one shot
    from .schema import load_or_fetch
    load_or_fetch(client=None, path=path, refresh=True, storage=storage)

    # Update catalog
    catalog = _load_catalog(storage)
    catalog[path] = {
        "name": meta.get("name", path),
        "rows": len(df),
        "frequency": frequency,
        "downloaded_at": meta_snapshot["downloaded_at"],
        "schema_cached": True,
    }
    _save_catalog(catalog, storage)

    console.print(f"[green]Saved {len(df):,} rows → {storage.uri(parquet_key)}[/green]")
    return storage.uri(parquet_key)


def status(storage: Storage | None = None) -> None:
    """Print a table of all locally downloaded datasets."""
    from rich.table import Table

    if storage is None:
        storage = default_storage()

    catalog = _load_catalog(storage)
    if not catalog:
        console.print("[dim]No datasets downloaded yet. Run: energy download <path>[/dim]")
        return

    table = Table(title="Local Dataset Catalog", show_lines=False)
    table.add_column("Path", style="green")
    table.add_column("Name")
    table.add_column("Frequency")
    table.add_column("Rows", justify="right")
    table.add_column("Downloaded")

    for path, info in sorted(catalog.items()):
        dt = info.get("downloaded_at", "")[:10]
        table.add_row(
            path,
            info.get("name", ""),
            info.get("frequency", ""),
            f"{info.get('rows', 0):,}",
            dt,
        )

    console.print(table)
