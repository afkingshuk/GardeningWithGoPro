# GoPro Gardening Pipeline

A GitHub-backed, VS Code-friendly pipeline for syncing timelapse images from a GoPro MAX, organizing them by capture date, rendering one video per day, and uploading completed daily videos to a NAS.

## Intended workflow

- Linux Mint box runs unattended.
- Hourly job:
  - runs sync in configured mode (`wifi` or `sdcard`)
  - `wifi`: joins GoPro Wi-Fi, syncs missing images from `http://10.5.5.9:8080/videos/DCIM/`, then returns to home Wi-Fi
  - `sdcard`: scans the mounted SD card `DCIM` tree, copies missing files into workspace raw storage, and registers them in SQLite
  - organizes images by capture date in both modes
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
- GoPro media extensions to sync (for example `.jpg`, `.jpeg`, `.gpr`)
- sync source (`wifi` or `sdcard`)
- SD card source directory (either the `DCIM` folder or its mount root)
- Home Wi-Fi connection name in NetworkManager
- workspace path
- NAS mount method / mount point / target path
- encoding profile (`quality` or `fast`) plus codec / fps / CRF
- timezone
- sync retry settings

## Required Mint-specific values

Set these in `config/config.local.yaml` before relying on the timers:

- `app.workspace`: defaults to `../GardeningWithGoProStorage`, which puts data/state/logs one level above the repo clone.
- `gopro.wifi_connection_name`: the NetworkManager connection profile name for the GoPro Wi-Fi.
- `gopro.media_extensions`: extensions eligible for sync. Default includes `.jpg`, `.jpeg`, and `.gpr`.
- `sync.source`: `wifi` (default) or `sdcard`.
- `sdcard.source_dir`: path to your SD card mount root or DCIM folder. Required when using `sync.source: sdcard`. `~` and env vars such as `$USER` are supported.
- `sdcard.show_progress`: enable single-line live progress in terminal during SD import.
- `sdcard.estimated_copy_speed_mb_per_sec`: used for SD import ETA estimate shown at pre-scan.
- `home_network.wifi_connection_name`: the NetworkManager connection profile name for your normal Wi-Fi.
- `nas.enabled`: defaults to `false`. Turn it on only after you finish the NAS configuration below.
- `nas.mount_point`: where the NAS will be mounted on Mint.
- `nas.target_dir`: destination directory on the mounted NAS share.
- `nas.mount_method`: use `fstab` if the mount is defined in `/etc/fstab`, or `cifs` for a direct SMB mount from the app.
- `nas.share`: required when `nas.mount_method: cifs`.
- `nas.credentials_file`: recommended for SMB credentials, for example `~/.smbcredentials-gopro`.
- `nas.use_sudo`: set to `true` if mount point creation or mount/umount require `sudo -n`.
- `nas.mount_options`: optional extra mount options for SMB.
- `sync.stable_file_min_age_seconds`: uses remote timestamps when available (GoPro directory `Modified` column and HTTP `Last-Modified`); if missing, files are treated as eligible immediately.
- `sync.max_retries`: how many attempts to make before leaving a file for the next cycle.
- `encoding.profile`: choose `quality` (default) or `fast`.
- `encoding.profiles.<name>`: profile overrides applied on top of base encoding settings.
- `encoding.fps`, `encoding.codec`: optional global encoding overrides.
- `encoding.profiles.quality` / `encoding.profiles.fast`: recommended place to customize `preset` and `crf`.
- `app.timezone`: should match the timezone you want to use when deciding whether a capture date is "today".

NAS scripts are now wrappers around the Python CLI. You normally do not edit them unless you want a fully custom mount flow:

- `scripts/mount_nas.sh`
- `scripts/unmount_nas.sh`

`config/wifi_profiles.yaml` is currently just a reference file. The application reads `config.yaml` and `config.local.yaml`.

## NAS Setup

Recommended unattended Mint setup:

1. Create a local credentials file such as `~/.smbcredentials-gopro` with your SMB username/password.
2. Run `chmod 600 ~/.smbcredentials-gopro`.
3. Make sure the NetworkManager profiles named in `config.local.yaml` actually exist on Mint.
   For the GoPro profile, the simplest path is to turn on the GoPro Wi-Fi and connect to it once manually in the Mint network UI so NetworkManager saves the profile.
4. Choose one of these approaches:

- `nas.mount_method: fstab`
  Add an `/etc/fstab` entry for `/mnt/knas` that uses your credentials file, then let the app call `mount /mnt/knas` and `umount /mnt/knas`.
- `nas.mount_method: cifs`
  Set `nas.share`, `nas.credentials_file`, and usually `nas.use_sudo: true` if the mount is under `/mnt`.

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
PYTHONPATH=src python -m gopro_gardening.cli sync --source wifi
PYTHONPATH=src python -m gopro_gardening.cli sync --source sdcard
PYTHONPATH=src python -m gopro_gardening.cli encode-upload
PYTHONPATH=src python -m gopro_gardening.cli healthcheck
PYTHONPATH=src python -m gopro_gardening.cli mount-nas
PYTHONPATH=src python -m gopro_gardening.cli unmount-nas
PYTHONPATH=src python -m gopro_gardening.cli ui --host 127.0.0.1 --port 8787
```

## Fast Mode Toggle

For faster backlog rendering, set this in `config/config.local.yaml`:

```yaml
encoding:
  profile: fast
```

Built-in profiles:

- `quality`: `preset: medium`, `crf: 18`
- `fast`: `preset: veryfast`, `crf: 22`

## Web Dashboard

If you prefer UI over CLI, run:

```bash
bash scripts/run_ui.sh
```

Then open `http://127.0.0.1:8787` in your browser. The dashboard provides buttons for:

- Sync (Wi-Fi)
- Sync (SD card)
- Encode + Upload
- Healthcheck
- Mount / Unmount NAS

Note: full Quik-style USB camera command/control depends on camera model and firmware. For the original GoPro MAX, use Wi-Fi control and SD ingest paths in this project.

## Notes

- The sync engine only downloads missing files.
- Wi-Fi sync and SD card sync share the same SQLite state, so files imported via SD card are not re-downloaded later via Wi-Fi.
- SD card sync performs a pre-scan and reports `remote_total`, `eligible_total`, `actionable_total`, `copyable_total`, estimated copy time, and live progress.
- Sync stats now include `remote_total` and `eligible_total` so you can verify what the camera exposed vs what passed extension filters.
- Sync stats include `ignored_extension` for files filtered out by `gopro.media_extensions`.
- Interrupted downloads are resumed from `.part` files when the GoPro server supports HTTP range requests.
- GoPro Wi-Fi sync may fail while the camera is actively capturing; the next scheduled run should retry once the camera is idle and the Wi-Fi API is available again.
- Capture date is determined from EXIF first, then filesystem mtime.
- File discovery is done by recursively crawling `http://10.5.5.9:8080/videos/DCIM/` and collecting files from all reachable subfolders.
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
