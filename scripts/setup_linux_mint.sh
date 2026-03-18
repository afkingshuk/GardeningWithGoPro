#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg rsync libimage-exiftool-perl network-manager cifs-utils

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p data/raw data/indexed data/renders data/reports logs state

echo "[OK] setup complete"
