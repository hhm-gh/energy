#!/usr/bin/env python3
"""
energy — EIA Open Data CLI

Usage:
    python main.py inventory [OPTIONS]

Options:
    --depth INT         How many levels deep to traverse (default: 2)
    --path TEXT         Start from a sub-route, e.g. "electricity"
    --descriptions      Show route descriptions
    --flat              Print a flat list of queryable endpoints instead of a tree
    --api-key TEXT      API key (overrides EIA_API_KEY env var)
"""

import argparse
import sys

from eia.client import EIAClient, EIAError
from eia.inventory import fetch_inventory, print_inventory, print_leaf_list


def cmd_inventory(args: argparse.Namespace) -> None:
    try:
        client = EIAClient(api_key=args.api_key)
    except EIAError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching EIA route tree (depth={args.depth}, path='{args.path or '/'}')\n")
    try:
        routes = fetch_inventory(client, path=args.path, depth=args.depth)
    except EIAError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.flat:
        print_leaf_list(routes)
    else:
        print_inventory(routes, show_descriptions=args.descriptions)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="energy",
        description="EIA energy data CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inv = sub.add_parser("inventory", help="Show available EIA datasets")
    inv.add_argument("--depth", type=int, default=2, help="Traversal depth (default: 2)")
    inv.add_argument("--path", default="", help="Start path, e.g. 'electricity'")
    inv.add_argument("--descriptions", action="store_true", help="Show route descriptions")
    inv.add_argument("--flat", action="store_true", help="Flat list of queryable endpoints")
    inv.add_argument("--api-key", default=None, help="EIA API key")

    args = parser.parse_args()

    if args.command == "inventory":
        cmd_inventory(args)


if __name__ == "__main__":
    main()
