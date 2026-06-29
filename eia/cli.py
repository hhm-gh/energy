import argparse
import sys

from .client import EIAClient, EIAError
from .inventory import fetch_inventory, print_inventory, print_leaf_list
from .publications import print_pub_list
from .pub_catalog import ELECTRICITY_ANNUAL
from .pub_downloader import download_table, pub_status
from .bulk import fetch_manifest, print_bulk_list
from .bulk_downloader import bulk_status, download_bulk, parse_bulk


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


def cmd_download(args: argparse.Namespace) -> None:
    from .downloader import download

    try:
        client = EIAClient(api_key=args.api_key)
    except EIAError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        download(client, args.path, frequency=args.frequency)
    except (EIAError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_status(_args: argparse.Namespace) -> None:
    from .downloader import status
    status()


def cmd_schema(args: argparse.Namespace) -> None:
    from .schema import load_or_fetch, print_paths, print_schema

    if not args.path:
        print_paths()
        return

    # Client only needed if schema isn't cached yet
    try:
        client = EIAClient(api_key=args.api_key)
    except EIAError as e:
        client = None  # will fail gracefully inside load_or_fetch if cache missing

    try:
        schema = load_or_fetch(client, args.path, refresh=args.refresh)
    except (EIAError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print_schema(args.path, schema)


def cmd_pub_list(args: argparse.Namespace) -> None:
    print_pub_list(ELECTRICITY_ANNUAL, chapter=args.chapter)


def cmd_pub_download(args: argparse.Namespace) -> None:
    try:
        download_table(args.table_id, pub_id=args.pub)
    except (ValueError, Exception) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_pub_status(_args: argparse.Namespace) -> None:
    pub_status()


def cmd_bulk_list(args: argparse.Namespace) -> None:
    try:
        datasets = fetch_manifest()
    except Exception as e:
        print(f"Error fetching manifest: {e}", file=sys.stderr)
        sys.exit(1)
    print_bulk_list(datasets, expand_aeo=args.aeo)


def cmd_bulk_download(args: argparse.Namespace) -> None:
    try:
        download_bulk(args.id)
    except (ValueError, Exception) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_bulk_parse(args: argparse.Namespace) -> None:
    try:
        parse_bulk(args.id)
    except (ValueError, Exception) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_bulk_status(_args: argparse.Namespace) -> None:
    bulk_status()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="energy",
        description="EIA energy data CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inv = sub.add_parser("inventory", help="Browse available EIA datasets")
    inv.add_argument("--depth", type=int, default=2, help="Traversal depth (default: 2)")
    inv.add_argument("--path", default="", help="Start path, e.g. 'electricity'")
    inv.add_argument("--descriptions", action="store_true", help="Show route descriptions")
    inv.add_argument("--flat", action="store_true", help="Flat list of queryable endpoints")
    inv.add_argument("--api-key", default=None, help="EIA API key")

    dl = sub.add_parser("download", help="Download a dataset to local Parquet")
    dl.add_argument("path", help="Dataset path, e.g. 'electricity/retail-sales'")
    dl.add_argument("--frequency", default=None, help="Frequency id, e.g. 'monthly' (default: first available)")
    dl.add_argument("--api-key", default=None, help="EIA API key")

    sub.add_parser("status", help="Show locally downloaded datasets")

    sc = sub.add_parser("schema", help="Show schema and summary for a dataset (no path = list all known)")
    sc.add_argument("path", nargs="?", default=None, help="Dataset path, e.g. 'electricity/retail-sales' (omit to list all known paths)")
    sc.add_argument("--refresh", action="store_true", help="Re-fetch from API even if cached")
    sc.add_argument("--api-key", default=None, help="EIA API key")

    pl = sub.add_parser("pub-list", help="List EIA Excel publication tables (Electric Power Annual)")
    pl.add_argument("--chapter", default=None, help="Filter by chapter number, e.g. '11' or 'A'")

    pd_ = sub.add_parser("pub-download", help="Download a publication table to local Parquet")
    pd_.add_argument("table_id", help="Table id, e.g. 'epa_11_03'")
    pd_.add_argument("--pub", default="electricity-annual", help="Publication id (default: electricity-annual)")

    sub.add_parser("pub-status", help="Show locally downloaded publication tables")

    bl = sub.add_parser("bulk-list", help="List EIA bulk download datasets from the live manifest")
    bl.add_argument("--aeo", action="store_true", help="Expand all Annual Energy Outlook year-vintages")

    bd = sub.add_parser("bulk-download", help="Download a bulk dataset ZIP and extract NDJSON")
    bd.add_argument("id", help="Dataset ID, e.g. 'ELEC'")

    bp = sub.add_parser("bulk-parse", help="Parse downloaded bulk NDJSON into Parquet files")
    bp.add_argument("id", help="Dataset ID, e.g. 'ELEC'")

    sub.add_parser("bulk-status", help="Show downloaded bulk datasets")

    args = parser.parse_args()

    if args.command == "inventory":
        cmd_inventory(args)
    elif args.command == "download":
        cmd_download(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "schema":
        cmd_schema(args)
    elif args.command == "pub-list":
        cmd_pub_list(args)
    elif args.command == "pub-download":
        cmd_pub_download(args)
    elif args.command == "pub-status":
        cmd_pub_status(args)
    elif args.command == "bulk-list":
        cmd_bulk_list(args)
    elif args.command == "bulk-download":
        cmd_bulk_download(args)
    elif args.command == "bulk-parse":
        cmd_bulk_parse(args)
    elif args.command == "bulk-status":
        cmd_bulk_status(args)


if __name__ == "__main__":
    main()
