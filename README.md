# GoPro Gardening Pipeline

A GitHub-backed, VS Code-friendly pipeline for syncing timelapse images from a GoPro MAX, organizing them by capture date, rendering one video per day, and uploading completed daily videos to a NAS.

## Intended workflow

- Linux Mint box runs unattended.
- Hourly job:
  - joins GoPro Wi-Fi
  - syncs missing images from `http://10.5.5.9:8080/videos/DCIM/`
  - organizes images by capture date
  - returns to home Wi-Fi
- Midnight job:
  - renders one 24-hour video per capture date
  - uploads the finished video to NAS
  - writes a daily report
- If a day or multiple days were missed, the next successful sync catches up by downloading any missing images. The midnight job renders any complete, unrendered past days.

## Repository layout

```text
gopro-gardening-pipeline/
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example
├── config/
├── scripts/
├── systemd/
├── src/gopro_gardening/
├── tests/
├── state/
├── logs/
└── data/
```

## Quick start on Linux Mint

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg rsync libimage-exiftool-perl network-manager cifs-utils
git clone <your-repo-url> ~/repos/gopro-gardening-pipeline
cd ~/repos/gopro-gardening-pipeline
bash scripts/setup_linux_mint.sh
cp config/config.local.example.yaml config/config.local.yaml
# edit config.local.yaml with your Mint-specific values
source .venv/bin/activate
PYTHONPATH=src python -m gopro_gardening.cli healthcheck
# if NAS is enabled, test it before enabling timers:
# PYTHONPATH=src python -m gopro_gardening.cli mount-nas
# PYTHONPATH=src python -m gopro_gardening.cli unmount-nas
bash scripts/install_systemd.sh
```

## Configuration

Use `config/config.local.yaml` for machine-specific settings. The loader reads:

1. `config/config.yaml`
2. `config/config.local.yaml` if present
3. `APP_CONFIG_PATH` if you want to point to a different config file

Important fields:

- GoPro Wi-Fi connection name in NetworkManager
- Home Wi-Fi connection name in NetworkManager
- workspace path
- NAS mount method / mount point / target path
- codec / fps / CRF
- timezone
- sync retry / stability settings

## Required Mint-specific values

Set these in `config/config.local.yaml` before relying on the timers:

- `app.workspace`: defaults to `../GardeningWithGoProStorage`, which puts data/state/logs one level above the repo clone.
- `gopro.wifi_connection_name`: the NetworkManager connection profile name for the GoPro Wi-Fi.
- `home_network.wifi_connection_name`: the NetworkManager connection profile name for your normal Wi-Fi.
- `nas.enabled`: defaults to `false`. Turn it on only after you finish the NAS configuration below.
- `nas.mount_point`: where the NAS will be mounted on Mint.
- `nas.target_dir`: destination directory on the mounted NAS share.
- `nas.mount_method`: use `fstab` if the mount is defined in `/etc/fstab`, or `cifs` for a direct SMB mount from the app.
- `nas.share`: required when `nas.mount_method: cifs`.
- `nas.credentials_file`: recommended for SMB credentials, for example `~/.smbcredentials-gopro`.
- `nas.use_sudo`: set to `true` if your mount/umount commands require `sudo -n`.
- `nas.mount_options`: optional extra mount options for SMB.
- `sync.stable_file_min_age_seconds`: how long a remote file must be unchanged before it is eligible to sync.
- `sync.max_retries`: how many attempts to make before leaving a file for the next cycle.
- `encoding.fps`, `encoding.codec`, `encoding.crf`, `encoding.preset`: optional encoding overrides.
- `app.timezone`: should match the timezone you want to use when deciding whether a capture date is "today".

NAS scripts are now wrappers around the Python CLI. You normally do not edit them unless you want a fully custom mount flow:

- `scripts/mount_nas.sh`
- `scripts/unmount_nas.sh`

`config/wifi_profiles.yaml` is currently just a reference file. The application reads `config.yaml` and `config.local.yaml`.

## NAS Setup

Recommended unattended Mint setup:

1. Create a local credentials file such as `~/.smbcredentials-gopro` with your SMB username/password.
2. Run `chmod 600 ~/.smbcredentials-gopro`.
3. Choose one of these approaches:

- `nas.mount_method: fstab`
  Add an `/etc/fstab` entry for `/mnt/knas` that uses your credentials file, then let the app call `mount /mnt/knas` and `umount /mnt/knas`.
- `nas.mount_method: cifs`
  Set `nas.share`, `nas.credentials_file`, and optionally `nas.use_sudo: true` if the mount requires `sudo -n`.

## Development from main PC

1. Edit in VS Code.
2. Commit and push to GitHub.
3. SSH into the Linux Mint box and run:

```bash
cd ~/repos/gopro-gardening-pipeline
bash scripts/pull_and_restart.sh
```

## Manual commands

```bash
source .venv/bin/activate
pytest -q
PYTHONPATH=src python -m gopro_gardening.cli sync
PYTHONPATH=src python -m gopro_gardening.cli encode-upload
PYTHONPATH=src python -m gopro_gardening.cli healthcheck
PYTHONPATH=src python -m gopro_gardening.cli mount-nas
PYTHONPATH=src python -m gopro_gardening.cli unmount-nas
```

## Notes

- The sync engine only downloads missing files.
- Interrupted downloads are resumed from `.part` files when the GoPro server supports HTTP range requests.
- Capture date is determined from EXIF first, then filesystem mtime.
- If the GoPro media-list API provides timestamps, synced files inherit that remote timestamp so fallback ordering is still meaningful.
- Images are organized by capture date, not sync time.
- The renderer skips the current date by default and only renders past, complete days.
- Daily encoding uses timestamps recorded in SQLite, not just filename sort order.
- Rendering is idempotent; a rendered day is recorded in SQLite.
- Uploading is idempotent; an uploaded day is recorded in SQLite.

## Suggested NAS strategy

Mount the NAS when needed, then upload rendered videos and reports with `rsync`. NAS uploads are disabled by default until you configure NAS settings and set `nas.enabled: true`.

## Suggested scheduling

- `gopro-sync.timer`: hourly
- `gopro-encode.timer`: daily at `00:05`

## Next implementation steps

Before unattended deployment, you will still want to customize:

- NAS share / credentials file or `/etc/fstab` entry
- any codec preferences
- sync retry / stability settings
- optional health notifications
