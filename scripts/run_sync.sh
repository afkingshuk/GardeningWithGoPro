#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source .venv/bin/activate
export PYTHONPATH=src
if [[ -n "${SYNC_SOURCE:-}" ]]; then
  python -m gopro_gardening.cli sync --source "$SYNC_SOURCE"
else
  python -m gopro_gardening.cli sync
fi
