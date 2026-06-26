import argparse
import sys

from .client import EIAClient, EIAError
from .inventory import fetch_inventory, print_inventory, print_leaf_list


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

    args = parser.parse_args()

    if args.command == "inventory":
        cmd_inventory(args)
    elif args.command == "download":
        cmd_download(args)
    elif args.command == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
