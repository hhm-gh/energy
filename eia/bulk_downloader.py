"""
Download and parse EIA bulk ZIP files.

Phase 2 — Download:
  energy bulk-download <ID>   stream ZIP → data/bulk/<ID>/raw.ndjson
  energy bulk-status          show downloaded bulk datasets

Phase 3 — Parse:
  energy bulk-parse <ID>      parse raw.ndjson → series.parquet, series_meta.parquet,
                               categories.parquet, category_series.parquet

Storage layout:
  data/bulk/<ID>/raw.ndjson
  data/bulk/<ID>/manifest.json
  data/bulk/<ID>/series.parquet
  data/bulk/<ID>/series_meta.parquet
  data/bulk/<ID>/categories.parquet
  data/bulk/<ID>/category_series.parquet
  data/bulk_catalog.json
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from .bulk import fetch_manifest
from .storage import Storage, default_storage

console = Console()

BULK_CATALOG_KEY = "bulk_catalog.json"
CHUNK_ROWS = 100_000


def _load_catalog(storage: Storage) -> dict:
    if storage.exists(BULK_CATALOG_KEY):
        return json.loads(storage.read_text(BULK_CATALOG_KEY))
    return {}


def _save_catalog(catalog: dict, storage: Storage) -> None:
    storage.write_text(BULK_CATALOG_KEY, json.dumps(catalog, indent=2))


def _bulk_dir(dataset_id: str, storage: Storage) -> Path:
    """Local path to data/bulk/<ID>/. Only valid for LocalStorage."""
    return Path(storage.uri(f"bulk/{dataset_id}"))


def _file_size_mb(path: Path) -> float:
    return path.stat().st_size / 1_048_576


# ---------------------------------------------------------------------------
# Phase 2 — Download
# ---------------------------------------------------------------------------

def download_bulk(dataset_id: str, storage: Storage | None = None) -> None:
    """Stream-download <ID>.zip, extract NDJSON, record metadata."""
    if storage is None:
        storage = default_storage()

    datasets = fetch_manifest()
    if dataset_id not in datasets:
        raise ValueError(
            f"Unknown dataset '{dataset_id}'. Run 'energy bulk-list' to see available IDs."
        )

    entry = datasets[dataset_id]
    url = entry["accessURL"]
    name = entry.get("name", dataset_id)

    console.print(f"\nDownloading [bold]{name}[/bold] ({dataset_id})")
    console.print(f"[dim]{url}[/dim]")

    out_dir = _bulk_dir(dataset_id, storage)
    out_dir.mkdir(parents=True, exist_ok=True)
    ndjson_path = out_dir / "raw.ndjson"

    # Stream ZIP to a temp file with progress bar
    req = urllib.request.Request(url, headers={"User-Agent": "energy-cli/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total_bytes = int(resp.headers.get("Content-Length", 0)) or None

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Downloading", total=total_bytes)
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))

            # Extract — bulk ZIPs contain exactly one NDJSON file
            console.print("Extracting...")
            with zipfile.ZipFile(tmp_path) as zf:
                names = zf.namelist()
                ndjson_members = [n for n in names if n.endswith(".txt") or n.endswith(".json")]
                if not ndjson_members:
                    ndjson_members = names  # fall back to first file
                member = ndjson_members[0]
                with zf.open(member) as src, open(ndjson_path, "wb") as dst:
                    while True:
                        chunk = src.read(65536)
                        if not chunk:
                            break
                        dst.write(chunk)

        finally:
            os.unlink(tmp_path)

    # Count lines and record metadata
    console.print("Counting records...")
    line_count = sum(1 for _ in open(ndjson_path, "rb"))
    file_size_mb = _file_size_mb(ndjson_path)

    manifest_data = {
        "id": dataset_id,
        "name": name,
        "description": entry.get("description", ""),
        "temporal": entry.get("temporal", ""),
        "spatial": entry.get("spatial", ""),
        "last_updated": entry.get("last_updated", ""),
        "access_url": url,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "raw_size_mb": round(file_size_mb, 2),
        "line_count": line_count,
        "parsed": False,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest_data, indent=2))

    catalog = _load_catalog(storage)
    catalog[dataset_id] = {
        "name": name,
        "temporal": entry.get("temporal", ""),
        "raw_size_mb": round(file_size_mb, 2),
        "line_count": line_count,
        "downloaded_at": manifest_data["downloaded_at"],
        "parsed": False,
    }
    _save_catalog(catalog, storage)

    console.print(
        f"[green]Saved {line_count:,} records ({file_size_mb:.1f} MB) → {ndjson_path}[/green]"
    )


# ---------------------------------------------------------------------------
# Phase 3 — Parse
# ---------------------------------------------------------------------------

_SERIES_SCHEMA = pa.schema([
    pa.field("series_id", pa.string()),
    pa.field("period", pa.string()),
    pa.field("value", pa.float64()),
])

_META_SCHEMA = pa.schema([
    pa.field("series_id", pa.string()),
    pa.field("name", pa.string()),
    pa.field("units", pa.string()),
    pa.field("f", pa.string()),
    pa.field("geography", pa.string()),
    pa.field("start", pa.string()),
    pa.field("end", pa.string()),
])

_CAT_SCHEMA = pa.schema([
    pa.field("category_id", pa.string()),
    pa.field("name", pa.string()),
    pa.field("parent_category_id", pa.string()),
])

_CAT_SERIES_SCHEMA = pa.schema([
    pa.field("category_id", pa.string()),
    pa.field("series_id", pa.string()),
])


def parse_bulk(dataset_id: str, storage: Storage | None = None) -> None:
    """Parse raw.ndjson → series.parquet, series_meta.parquet, categories.parquet, category_series.parquet."""
    if storage is None:
        storage = default_storage()

    out_dir = _bulk_dir(dataset_id, storage)
    ndjson_path = out_dir / "raw.ndjson"
    manifest_path = out_dir / "manifest.json"

    if not ndjson_path.exists():
        raise ValueError(
            f"No raw data for '{dataset_id}'. Run 'energy bulk-download {dataset_id}' first."
        )

    manifest_data = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    total_lines = manifest_data.get("line_count", 0)
    name = manifest_data.get("name", dataset_id)

    console.print(f"\nParsing [bold]{name}[/bold] ({dataset_id})")
    if total_lines:
        console.print(f"[dim]{total_lines:,} records[/dim]")

    series_path      = out_dir / "series.parquet"
    meta_path        = out_dir / "series_meta.parquet"
    cat_path         = out_dir / "categories.parquet"
    cat_series_path  = out_dir / "category_series.parquet"

    # Remove existing outputs so we start fresh
    for p in (series_path, meta_path, cat_path, cat_series_path):
        if p.exists():
            p.unlink()

    series_writer: pq.ParquetWriter | None = None
    series_chunk: list[dict] = []

    meta_rows: list[dict] = []
    cat_rows: list[dict] = []
    cat_series_rows: list[dict] = []

    series_count = 0
    category_count = 0
    skipped = 0

    # child_to_parent[child_id] = parent_id — built during the single parse pass
    child_to_parent: dict[str, str] = {}

    def _flush_series_chunk() -> None:
        nonlocal series_writer
        if not series_chunk:
            return
        table = pa.Table.from_pylist(series_chunk, schema=_SERIES_SCHEMA)
        if series_writer is None:
            series_writer = pq.ParquetWriter(str(series_path), _SERIES_SCHEMA)
        series_writer.write_table(table)
        series_chunk.clear()

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Parsing", total=total_lines or None)

        with open(ndjson_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    progress.update(task, advance=1)
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    progress.update(task, advance=1)
                    continue

                if "series_id" in record:
                    sid = record["series_id"]
                    data = record.get("data") or []
                    for point in data:
                        if len(point) == 2:
                            period, val = point
                            series_chunk.append({
                                "series_id": sid,
                                "period": str(period) if period is not None else None,
                                "value": float(val) if val is not None else None,
                            })
                    if len(series_chunk) >= CHUNK_ROWS:
                        _flush_series_chunk()

                    meta_rows.append({
                        "series_id": sid,
                        "name": record.get("name", ""),
                        "units": record.get("units", ""),
                        "f": record.get("f", ""),
                        "geography": record.get("geography", ""),
                        "start": record.get("start", ""),
                        "end": record.get("end", ""),
                    })
                    series_count += 1

                elif "category_id" in record:
                    cid = str(record["category_id"])
                    # parent_category_id may be on the record directly (EMISS format)
                    # or derivable from childcategories on the parent record (other formats)
                    direct_parent = record.get("parent_category_id")
                    if direct_parent is not None:
                        child_to_parent[cid] = str(direct_parent)
                    cat_rows.append({
                        "category_id": cid,
                        "name": record.get("name", ""),
                        "parent_category_id": None,  # filled after loop
                    })
                    for child in record.get("childcategories", []):
                        # childcategories may be dicts {"category_id": ...} or strings
                        child_id = child["category_id"] if isinstance(child, dict) else child
                        child_to_parent[str(child_id)] = cid
                    for cs in record.get("childseries", []):
                        # childseries may be dicts {"series_id": ...} or plain strings
                        sid = cs["series_id"] if isinstance(cs, dict) else cs
                        cat_series_rows.append({
                            "category_id": cid,
                            "series_id": sid,
                        })
                    category_count += 1

                else:
                    skipped += 1

                progress.update(task, advance=1)

    # Resolve parent_category_id now that the full tree is known
    for row in cat_rows:
        row["parent_category_id"] = child_to_parent.get(row["category_id"])

    # --- write remaining series chunk ---
    _flush_series_chunk()
    if series_writer:
        series_writer.close()

    # --- write metadata tables ---
    console.print("Writing metadata tables...")

    pa.parquet.write_table(
        pa.Table.from_pylist(meta_rows, schema=_META_SCHEMA),
        str(meta_path),
    )
    pa.parquet.write_table(
        pa.Table.from_pylist(cat_rows, schema=_CAT_SCHEMA),
        str(cat_path),
    )
    pa.parquet.write_table(
        pa.Table.from_pylist(cat_series_rows, schema=_CAT_SERIES_SCHEMA),
        str(cat_series_path),
    )

    # --- update manifest and catalog ---
    manifest_data["parsed"] = True
    manifest_data["series_count"] = series_count
    manifest_data["category_count"] = category_count
    manifest_path.write_text(json.dumps(manifest_data, indent=2))

    catalog = _load_catalog(storage)
    if dataset_id in catalog:
        catalog[dataset_id]["parsed"] = True
        catalog[dataset_id]["series_count"] = series_count
        catalog[dataset_id]["category_count"] = category_count
    _save_catalog(catalog, storage)

    total_data_rows = sum(
        pq.read_metadata(str(series_path)).row_group(i).num_rows
        for i in range(pq.read_metadata(str(series_path)).num_row_groups)
    ) if series_path.exists() else 0

    console.print(
        f"[green]Done — {series_count:,} series · {total_data_rows:,} data rows · "
        f"{category_count:,} categories[/green]"
    )
    if skipped:
        console.print(f"[yellow]Skipped {skipped:,} unrecognized lines[/yellow]")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def bulk_status(storage: Storage | None = None) -> None:
    """Print a table of all downloaded bulk datasets."""
    if storage is None:
        storage = default_storage()

    catalog = _load_catalog(storage)
    if not catalog:
        console.print(
            "[dim]No bulk datasets downloaded yet. Run: energy bulk-download <ID>[/dim]"
        )
        return

    table = Table(title="Downloaded Bulk Datasets", show_lines=False)
    table.add_column("ID", style="green", no_wrap=True)
    table.add_column("Name")
    table.add_column("Temporal")
    table.add_column("Size (MB)", justify="right")
    table.add_column("Lines", justify="right")
    table.add_column("Parsed", justify="center")
    table.add_column("Downloaded")

    for did, info in sorted(catalog.items()):
        dt = info.get("downloaded_at", "")[:10]
        parsed = "[green]yes[/green]" if info.get("parsed") else "[dim]no[/dim]"
        table.add_row(
            did,
            info.get("name", ""),
            info.get("temporal", ""),
            f"{info.get('raw_size_mb', 0):.1f}",
            f"{info.get('line_count', 0):,}",
            parsed,
            dt,
        )

    console.print(table)
