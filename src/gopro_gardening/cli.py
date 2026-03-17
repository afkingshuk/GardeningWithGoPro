from __future__ import annotations

import argparse
from pathlib import Path

from .main import build_context, run_encode_upload, run_healthcheck, run_sync


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GoPro Gardening pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync")
    sub.add_parser("encode-upload")
    sub.add_parser("healthcheck")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root_dir = Path(__file__).resolve().parents[2]
    context = build_context(root_dir)

    if args.command == "sync":
        run_sync(context)
    elif args.command == "encode-upload":
        run_encode_upload(context)
    elif args.command == "healthcheck":
        run_healthcheck(context)


if __name__ == "__main__":
    main()
