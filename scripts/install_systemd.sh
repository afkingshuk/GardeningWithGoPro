#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"

sed "s|__ROOT__|$ROOT_DIR|g" "$ROOT_DIR/systemd/gopro-sync.service" > "$USER_SYSTEMD_DIR/gopro-sync.service"
sed "s|__ROOT__|$ROOT_DIR|g" "$ROOT_DIR/systemd/gopro-sync.timer" > "$USER_SYSTEMD_DIR/gopro-sync.timer"
sed "s|__ROOT__|$ROOT_DIR|g" "$ROOT_DIR/systemd/gopro-encode.service" > "$USER_SYSTEMD_DIR/gopro-encode.service"
sed "s|__ROOT__|$ROOT_DIR|g" "$ROOT_DIR/systemd/gopro-encode.timer" > "$USER_SYSTEMD_DIR/gopro-encode.timer"

systemctl --user daemon-reload
systemctl --user enable --now gopro-sync.timer
systemctl --user enable --now gopro-encode.timer

echo "[OK] user timers installed"
echo "Run: loginctl enable-linger $USER"
