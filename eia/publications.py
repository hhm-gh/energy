"""
Display helpers for EIA Excel-based publications (non-API datasets).
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich import box

from .pub_catalog import ALL_PUBLICATIONS, ELECTRICITY_ANNUAL

console = Console()


def list_tables(publication: dict, chapter: str | None = None) -> list[dict]:
    """Return all tables for a publication, optionally filtered by chapter number."""
    rows = []
    for ch in publication["chapters"]:
        if chapter is not None and ch["number"].lower() != chapter.lower():
            continue
        for t in ch["tables"]:
            rows.append({
                "chapter_number": ch["number"],
                "chapter_title": ch["title"],
                **t,
            })
    return rows


def print_pub_list(publication: dict, chapter: str | None = None) -> None:
    tables = list_tables(publication, chapter)
    if not tables:
        console.print(f"[red]No tables found for chapter '{chapter}'.[/red]")
        return

    total = sum(len(ch["tables"]) for ch in publication["chapters"])
    header = f"[bold cyan]{publication['title']}[/bold cyan]"
    if chapter:
        header += f"  [dim]chapter {chapter}[/dim]"
    else:
        header += f"  [dim]{total} tables[/dim]"
    console.print(header)
    console.print()

    current_chapter = None
    for row in tables:
        if row["chapter_number"] != current_chapter:
            current_chapter = row["chapter_number"]
            console.print(
                f"  [bold]{current_chapter}  {row['chapter_title']}[/bold]"
            )
        num = row["number"]
        title = row["title"]
        console.print(f"    [green]{num:<8}[/green] {title}")

    console.print()
    console.print(f"[dim]{len(tables)} table(s) shown.[/dim]")
