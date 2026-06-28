"""
EIA bulk file manifest — listing and summary.

The manifest at https://www.eia.gov/opendata/bulk/manifest.txt is a JSON
file describing all available bulk download datasets. It is updated twice
daily (5 a.m. and 3 p.m. ET).
"""

from __future__ import annotations

import json
import re
import urllib.request

from rich.console import Console
from rich.table import Table

MANIFEST_URL = "https://www.eia.gov/opendata/bulk/manifest.txt"

console = Console()


def fetch_manifest() -> dict[str, dict]:
    """Fetch and parse the EIA bulk manifest. Returns the dataset dict keyed by id."""
    req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "energy-cli/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data["dataset"]


def _aeo_year(key: str) -> int | None:
    """Return the year for AEO.YEAR keys, None otherwise."""
    m = re.match(r"^AEO\.(\d{4})$", key)
    return int(m.group(1)) if m else None


def _spatial_abbrev(s: str) -> str:
    if not s:
        return ""
    # Keep up to first comma chunk or 30 chars
    chunk = s.split(",")[0].strip()
    return chunk[:30] if len(chunk) > 30 else chunk


def print_bulk_list(datasets: dict[str, dict], expand_aeo: bool = False) -> None:
    aeo_entries = {k: v for k, v in datasets.items() if _aeo_year(k) is not None}
    other_entries = {k: v for k, v in datasets.items() if k not in aeo_entries}

    total = len(datasets)
    aeo_count = len(aeo_entries)

    console.print(
        f"\n[bold cyan]EIA Bulk Files[/bold cyan]  "
        f"[dim]{total} datasets  ({aeo_count} AEO year-vintages + {total - aeo_count} current)[/dim]"
    )
    console.print(
        f"[dim]Manifest: {MANIFEST_URL}[/dim]\n"
    )

    table = Table(show_header=True, header_style="bold", show_lines=False, box=None, pad_edge=False)
    table.add_column("ID  (updated)", style="green", no_wrap=True, min_width=24)
    table.add_column("Name", min_width=30, max_width=40)
    table.add_column("Temporal", no_wrap=True)

    def add_row(key: str, entry: dict) -> None:
        updated = entry.get("last_updated", "")[:10]
        table.add_row(
            f"{key}  [dim]{updated}[/dim]",
            entry.get("name", ""),
            entry.get("temporal", ""),
        )

    # AEO block
    if expand_aeo:
        for key in sorted(aeo_entries):
            add_row(key, aeo_entries[key])
    else:
        years = sorted(y for y in (_aeo_year(k) for k in aeo_entries) if y)
        if years:
            year_range = f"{years[0]}–{years[-1]}"
            latest = max(aeo_entries.values(), key=lambda v: v.get("last_updated", ""))
            latest_date = latest.get("last_updated", "")[:10]
            table.add_row(
                f"[dim]AEO ({len(aeo_entries)} vintages)  {latest_date}[/dim]",
                f"Annual Energy Outlook {year_range}",
                "annual",
            )
        # AEO.IEO2 is not a year-vintage — show it separately
        if "AEO.IEO2" in datasets:
            add_row("AEO.IEO2", datasets["AEO.IEO2"])

    # All other datasets, alphabetical
    for key in sorted(other_entries):
        if key == "AEO.IEO2":
            continue  # already handled above
        add_row(key, other_entries[key])

    console.print(table)
    console.print(
        f"\n[dim]Download URL pattern: https://www.eia.gov/opendata/bulk/<ID>.zip[/dim]"
        "  Use [bold]--aeo[/bold] to expand year-vintage rows."
        if not expand_aeo
        else f"\n[dim]Download URL pattern: https://www.eia.gov/opendata/bulk/<ID>.zip[/dim]"
    )
