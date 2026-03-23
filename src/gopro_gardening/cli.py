from __future__ import annotations

import argparse
from pathlib import Path

from .main import (
    build_context,
    run_encode_upload,
    run_healthcheck,
    run_mount_nas,
    run_sync,
    run_unmount_nas,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GoPro Gardening pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sync_parser = sub.add_parser("sync")
    sync_parser.add_argument(
        "--source",
        default=None,
        help="Sync source override: wifi or sdcard (defaults to sync.source in config).",
    )
    sub.add_parser("encode-upload")
    sub.add_parser("healthcheck")
    sub.add_parser("mount-nas")
    sub.add_parser("unmount-nas")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root_dir = Path(__file__).resolve().parents[2]
    context = build_context(root_dir)

    if args.command == "sync":
        run_sync(context, source_override=args.source)
    elif args.command == "encode-upload":
        run_encode_upload(context)
    elif args.command == "healthcheck":
        run_healthcheck(context)
    elif args.command == "mount-nas":
        run_mount_nas(context)
    elif args.command == "unmount-nas":
        run_unmount_nas(context)


if __name__ == "__main__":
    main()
