"""
Traverse the EIA v2 API route tree and display an inventory of available datasets.

The v2 API is hierarchical: each route returns child routes and/or a data endpoint.
A route with no child routes is a data leaf (queryable with /data).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from rich.console import Console
from rich.tree import Tree

from .client import EIAClient

console = Console()


@dataclass
class Route:
    id: str
    name: str
    description: str = ""
    path: str = ""
    children: list[Route] = field(default_factory=list)
    is_leaf: bool = False  # True when the route has a /data endpoint


def _parse_routes(data: dict, parent_path: str) -> list[Route]:
    routes = []
    for r in data.get("routes", []):
        rid = r.get("id", "")
        path = f"{parent_path}/{rid}".lstrip("/")
        routes.append(
            Route(
                id=rid,
                name=r.get("name", rid),
                description=r.get("description", ""),
                path=path,
            )
        )
    return routes


def fetch_inventory(client: EIAClient, path: str = "", depth: int = 2) -> list[Route]:
    """
    Recursively fetch routes up to `depth` levels deep.
    depth=1  → top-level categories only
    depth=2  → categories + their direct children (default, covers most datasets)
    depth=3+ → full tree (slow, ~many requests)
    """
    data = client.get(path)
    routes = _parse_routes(data, path)

    for route in routes:
        if depth > 1:
            try:
                child_data = client.get(route.path)
                child_routes = _parse_routes(child_data, route.path)
                if child_routes:
                    route.children = child_routes
                    if depth > 2:
                        for child in route.children:
                            _fill_children(client, child, depth - 2)
                else:
                    route.is_leaf = True
            except Exception:
                route.is_leaf = True

    return routes


def _fill_children(client: EIAClient, route: Route, remaining: int) -> None:
    if remaining <= 0:
        return
    try:
        data = client.get(route.path)
        children = _parse_routes(data, route.path)
        if children:
            route.children = children
            for child in children:
                _fill_children(client, child, remaining - 1)
        else:
            route.is_leaf = True
    except Exception:
        route.is_leaf = True


def _iter_leaves(routes: list[Route]) -> Iterator[Route]:
    for r in routes:
        if r.is_leaf or not r.children:
            yield r
        else:
            yield from _iter_leaves(r.children)


def print_inventory(routes: list[Route], show_descriptions: bool = False) -> None:
    tree = Tree("[bold cyan]EIA Open Data API[/bold cyan]  [dim]api.eia.gov/v2[/dim]")
    _build_tree(tree, routes, show_descriptions)
    console.print(tree)

    leaves = list(_iter_leaves(routes))
    console.print(
        f"\n[dim]{len(leaves)} queryable dataset(s) found at this depth.[/dim]"
        "  Use [bold]--depth[/bold] to explore further."
    )


def _build_tree(parent: Tree, routes: list[Route], show_descriptions: bool) -> None:
    for route in routes:
        label = f"[bold]{route.name}[/bold]  [dim green]{route.path}[/dim green]"
        if route.is_leaf:
            label += "  [yellow]●[/yellow]"  # data leaf marker
        if show_descriptions and route.description:
            label += f"\n  [dim]{route.description[:120]}[/dim]"
        branch = parent.add(label)
        if route.children:
            _build_tree(branch, route.children, show_descriptions)


def print_leaf_list(routes: list[Route]) -> None:
    """Flat list of all queryable endpoints, suitable for piping."""
    for leaf in _iter_leaves(routes):
        console.print(f"[green]{leaf.path}[/green]  {leaf.name}")
