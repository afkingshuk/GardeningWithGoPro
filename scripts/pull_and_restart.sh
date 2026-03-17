#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

git pull --ff-only origin main
source .venv/bin/activate
pip install -r requirements.txt
systemctl --user daemon-reload
systemctl --user restart gopro-sync.timer gopro-encode.timer
systemctl --user status gopro-sync.timer --no-pager || true
systemctl --user status gopro-encode.timer --no-pager || true
