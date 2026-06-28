"""
Download EIA Excel publication tables and convert to local Parquet files.

Storage layout:
  data/publications/<pub-id>/<table-id>/data.parquet
  data/publications/<pub-id>/<table-id>/metadata.json
  data/pub_catalog.json
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

import openpyxl
import pandas as pd
from rich.console import Console

from .pub_catalog import ALL_PUBLICATIONS, table_xlsx_url
from .storage import Storage, default_storage

console = Console()

PUB_CATALOG_KEY = "pub_catalog.json"


def _load_pub_catalog(storage: Storage) -> dict:
    if storage.exists(PUB_CATALOG_KEY):
        return json.loads(storage.read_text(PUB_CATALOG_KEY))
    return {}


def _save_pub_catalog(catalog: dict, storage: Storage) -> None:
    storage.write_text(PUB_CATALOG_KEY, json.dumps(catalog, indent=2))


def _find_publication(pub_id: str) -> dict | None:
    for pub in ALL_PUBLICATIONS:
        if pub["id"] == pub_id:
            return pub
    return None


def _find_table(pub: dict, table_id: str) -> dict | None:
    for ch in pub["chapters"]:
        for t in ch["tables"]:
            if t["id"] == table_id:
                return {**t, "chapter_number": ch["number"], "chapter_title": ch["title"]}
    return None


def parse_xlsx(path: str) -> tuple[pd.DataFrame, bool]:
    """Best-effort parser for EIA Electric Power Annual xlsx files.

    Returns (df, is_clean) where is_clean=True means a single unambiguous
    header row was found — column names are exact. is_clean=False means
    multi-level merged-cell headers were joined heuristically (data is
    likely correct but column names may be verbose or slightly imprecise).

    Approach:
    1. Find the first row with float data in cols 1+ (data boundary)
    2. Collect header rows above it (skip single-cell section labels)
    3. Forward-fill merged cells, join levels with " / " into column names
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    # Find first row where any cell in cols 1+ is a float (actual data row)
    float_row_idx = None
    for i, row in enumerate(rows):
        if any(isinstance(v, float) for v in row[1:]):
            float_row_idx = i
            break

    if float_row_idx is None:
        float_row_idx = 1

    # Header rows: skip row 0 (title); keep rows with >=2 non-None values in cols 1+
    header_rows = []
    for row in rows[1:float_row_idx]:
        non_none_later = sum(1 for v in row[1:] if v is not None)
        if non_none_later >= 2:
            header_rows.append(row)

    is_clean = len(header_rows) == 1
    ncols = len(rows[0])

    def ffill(row: tuple) -> list[str | None]:
        result, last = [], None
        for v in row:
            if v is not None:
                cleaned = str(v).replace("\n", " ").strip()
                if cleaned:
                    last = cleaned
            result.append(last)
        return result

    if header_rows:
        filled = [ffill(r) for r in header_rows]
        col_names = []
        for j in range(ncols):
            parts, seen = [], set()
            for r in filled:
                val = r[j] if j < len(r) else None
                if val and val not in seen:
                    parts.append(val)
                    seen.add(val)
            col_names.append(" / ".join(parts) if parts else f"col_{j}")
    else:
        col_names = [f"col_{j}" for j in range(ncols)]

    df = pd.DataFrame(rows[float_row_idx:], columns=col_names)

    # Drop section-label rows (all numeric cols are None)
    numeric_cols = df.columns[1:]
    df = df.dropna(subset=numeric_cols, how="all")

    # Drop all-None columns (artifacts of sparse xlsx layouts)
    df = df.dropna(axis=1, how="all")

    df = df.reset_index(drop=True)
    return df, is_clean


def download_table(
    table_id: str,
    pub_id: str = "electricity-annual",
    storage: Storage | None = None,
) -> str:
    """Download a publication table's xlsx, parse it, and save as Parquet.

    Returns the storage URI of the saved Parquet file.
    """
    if storage is None:
        storage = default_storage()

    pub = _find_publication(pub_id)
    if pub is None:
        raise ValueError(f"Unknown publication '{pub_id}'")

    table_meta = _find_table(pub, table_id)
    if table_meta is None:
        raise ValueError(f"Table '{table_id}' not found in '{pub_id}'")

    xlsx_url = table_xlsx_url(pub, table_id)
    console.print(
        f"Downloading [bold]Table {table_meta['number']}[/bold] — {table_meta['title']}"
    )
    console.print(f"[dim]{xlsx_url}[/dim]")

    # Fetch xlsx into a temp file
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        req = urllib.request.Request(xlsx_url, headers={"User-Agent": "energy-cli/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(tmp_path, "wb") as f:
                f.write(resp.read())

        df, is_clean = parse_xlsx(tmp_path)
    finally:
        os.unlink(tmp_path)

    parse_quality = "clean" if is_clean else "best-effort"
    display_title = (
        f"{table_meta['title']} (clean)" if is_clean else table_meta["title"]
    )

    storage_prefix = f"publications/{pub_id}/{table_id}"
    parquet_key = f"{storage_prefix}/data.parquet"
    from pathlib import Path
    Path(storage.uri(parquet_key)).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(storage.uri(parquet_key), index=False)

    meta_snapshot = {
        "pub_id": pub_id,
        "pub_title": pub["title"],
        "table_id": table_id,
        "table_number": table_meta["number"],
        "table_title": display_title,
        "chapter_number": table_meta["chapter_number"],
        "chapter_title": table_meta["chapter_title"],
        "source_url": xlsx_url,
        "parse_quality": parse_quality,
        "rows": len(df),
        "columns": list(df.columns),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    storage.write_text(
        f"{storage_prefix}/metadata.json", json.dumps(meta_snapshot, indent=2)
    )

    catalog = _load_pub_catalog(storage)
    catalog[f"{pub_id}/{table_id}"] = {
        "pub_title": pub["title"],
        "table_number": table_meta["number"],
        "table_title": display_title,
        "parse_quality": parse_quality,
        "rows": len(df),
        "columns": len(df.columns),
        "downloaded_at": meta_snapshot["downloaded_at"],
    }
    _save_pub_catalog(catalog, storage)

    quality_tag = "  [cyan][clean][/cyan]" if is_clean else "  [dim][best-effort][/dim]"
    console.print(
        f"[green]Saved {len(df):,} rows × {len(df.columns)} cols → {storage.uri(parquet_key)}[/green]"
        + quality_tag
    )
    return storage.uri(parquet_key)


def pub_status(storage: Storage | None = None) -> None:
    """Print a table of all locally downloaded publication tables."""
    from rich.table import Table

    if storage is None:
        storage = default_storage()

    catalog = _load_pub_catalog(storage)
    if not catalog:
        console.print(
            "[dim]No publication tables downloaded yet. Run: energy pub-download <table-id>[/dim]"
        )
        return

    table = Table(title="Downloaded Publication Tables", show_lines=False)
    table.add_column("Table", style="green")
    table.add_column("Title")
    table.add_column("Quality")
    table.add_column("Rows", justify="right")
    table.add_column("Cols", justify="right")
    table.add_column("Downloaded")

    for key, info in sorted(catalog.items()):
        dt = info.get("downloaded_at", "")[:10]
        num = info.get("table_number", "")
        q = info.get("parse_quality", "")
        quality_str = "[cyan]clean[/cyan]" if q == "clean" else "[dim]best-effort[/dim]"
        table.add_row(
            f"{num}  ({key.split('/')[-1]})",
            info.get("table_title", ""),
            quality_str,
            f"{info.get('rows', 0):,}",
            str(info.get("columns", "")),
            dt,
        )

    console.print(table)
