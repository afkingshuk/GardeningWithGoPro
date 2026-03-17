#!/usr/bin/env bash
set -euo pipefail
# Replace this with your real NAS mount command.
# Example SMB mount:
# sudo mount -t cifs //10.0.0.44/incoming /mnt/knas -o username=YOURUSER,password=YOURPASS,uid=$(id -u),gid=$(id -g)
echo "Configure scripts/mount_nas.sh for your NAS before setting nas.enabled: true." >&2
exit 1
