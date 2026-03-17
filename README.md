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
sudo apt install -y python3-venv python3-pip ffmpeg rsync libimage-exiftool-perl network-manager
git clone <your-repo-url> ~/repos/gopro-gardening-pipeline
cd ~/repos/gopro-gardening-pipeline
bash scripts/setup_linux_mint.sh
cp config/config.local.example.yaml config/config.local.yaml
# edit config.local.yaml with your Mint-specific values
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
- NAS target path
- codec / fps / CRF
- timezone

## Required Mint-specific values

Set these in `config/config.local.yaml` before relying on the timers:

- `app.workspace`: defaults to `../GardeningWithGoProStorage`, which puts data/state/logs one level above the repo clone.
- `gopro.wifi_connection_name`: the NetworkManager connection profile name for the GoPro Wi-Fi.
- `home_network.wifi_connection_name`: the NetworkManager connection profile name for your normal Wi-Fi. Leave it empty only if you do not want the app to force a reconnect.
- `nas.enabled`: defaults to `false`. Turn it on only after you finish the NAS configuration below.
- `nas.mount_point`: where the NAS will be mounted on Mint.
- `nas.target_dir`: destination directory on the mounted NAS share.
- `encoding.fps`, `encoding.codec`, `encoding.crf`, `encoding.preset`: optional encoding overrides.
- `app.timezone`: should match the timezone you want to use when deciding whether a capture date is "today".

Also customize these scripts if NAS upload is enabled:

- `scripts/mount_nas.sh`: replace the placeholder with your real mount command.
- `scripts/unmount_nas.sh`: replace the placeholder if you want the share unmounted after upload.

`config/wifi_profiles.yaml` is currently just a reference file. The application reads `config.yaml` and `config.local.yaml`.

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
PYTHONPATH=src python -m gopro_gardening.cli sync
PYTHONPATH=src python -m gopro_gardening.cli encode-upload
PYTHONPATH=src python -m gopro_gardening.cli healthcheck
```

## Notes

- The sync engine only downloads missing files.
- Capture date is determined from EXIF first, then filesystem mtime.
- Images are organized by capture date, not sync time.
- The renderer skips the current date by default and only renders past, complete days.
- Rendering is idempotent; a rendered day is recorded in SQLite.
- Uploading is idempotent; an uploaded day is recorded in SQLite.

## Suggested NAS strategy

Mount the NAS when needed in `scripts/mount_nas.sh`, then upload rendered videos and reports with `rsync`. NAS uploads are disabled by default until you configure the mount script and set `nas.enabled: true`.

## Suggested scheduling

- `gopro-sync.timer`: hourly
- `gopro-encode.timer`: daily shortly after midnight

## Next implementation steps

This scaffold is functional enough to start, but you will still want to customize:

- exact NAS mount command
- Wi-Fi connection names
- codec preferences
- network retry behavior
- optional health notifications
