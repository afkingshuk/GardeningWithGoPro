from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config_loader import load_config
from .encoder import Encoder
from .gopro_client import GoProClient
from .logging_utils import configure_logging
from .nas import NASUploader
from .sdcard_sync import SDCardSyncEngine
from .state_db import StateDB
from .sync_engine import SyncEngine
from .wifi_manager import WifiManager

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    root_dir: Path
    config: Dict[str, Any]
    state_db: StateDB
    wifi: WifiManager
    client: GoProClient
    sync_engine: SyncEngine
    sdcard_sync: SDCardSyncEngine
    encoder: Encoder
    nas: NASUploader


def _resolve_path(base_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(os.path.expandvars(value)).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def _current_capture_date(config: Dict[str, Any]) -> str:
    timezone_name = config.get("app", {}).get("timezone", "UTC")
    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid app.timezone: {timezone_name}") from exc
    return datetime.now(tzinfo).date().isoformat()


def _resolve_target_dir(root_dir: Path, mount_point: Path | None, value: str) -> Path:
    target_dir = Path(value).expanduser()
    if target_dir.is_absolute():
        return target_dir
    if mount_point is not None:
        return (mount_point / target_dir).resolve()
    return (root_dir / target_dir).resolve()


def _normalize_sync_source(value: str) -> str:
    normalized = (value or "").strip().lower()
    aliases = {
        "wifi": "wifi",
        "gopro": "wifi",
        "camera": "wifi",
        "sd": "sdcard",
        "sdcard": "sdcard",
        "card": "sdcard",
        "memcard": "sdcard",
        "memorycard": "sdcard",
    }
    selected = aliases.get(normalized)
    if selected:
        return selected
    raise ValueError(f"Unsupported sync source: {value}. Expected one of: wifi, sdcard")


def build_context(root_dir: Path) -> AppContext:
    root_dir = root_dir.resolve()
    config = load_config(root_dir)

    workspace = _resolve_path(root_dir, config.get("app", {}).get("workspace", ".")) or root_dir.resolve()
    log_dir = workspace / config["paths"]["logs_dir"]
    configure_logging(log_dir, config["app"].get("log_level", "INFO"))

    state_db = StateDB(workspace / config["app"]["state_db"])
    wifi = WifiManager(
        gopro_connection=config["gopro"]["wifi_connection_name"],
        home_connection=config.get("home_network", {}).get("wifi_connection_name") or None,
    )
    client = GoProClient(
        base_url=config["gopro"]["base_url"],
        timeout=config["gopro"].get("request_timeout_seconds", 30),
        user_agent=config["sync"].get("user_agent", "gopro-gardening-pipeline/0.1"),
    )
    sync_engine = SyncEngine(
        client=client,
        state_db=state_db,
        raw_dir=workspace / config["paths"]["raw_dir"],
        indexed_dir=workspace / config["paths"]["indexed_dir"],
        media_extensions=config["gopro"]["media_extensions"],
        timezone_name=config["app"].get("timezone", "UTC"),
        stable_file_min_age_seconds=int(config["sync"].get("stable_file_min_age_seconds", 0)),
        retry_failed_downloads=bool(config["sync"].get("retry_failed_downloads", True)),
        max_retries=int(config["sync"].get("max_retries", 3)),
    )
    sdcard_sync = SDCardSyncEngine(
        state_db=state_db,
        source_dir=_resolve_path(root_dir, config.get("sdcard", {}).get("source_dir")),
        raw_dir=workspace / config["paths"]["raw_dir"],
        indexed_dir=workspace / config["paths"]["indexed_dir"],
        media_extensions=config["gopro"]["media_extensions"],
        timezone_name=config["app"].get("timezone", "UTC"),
    )
    encoder = Encoder(
        indexed_dir=workspace / config["paths"]["indexed_dir"],
        renders_dir=workspace / config["paths"]["renders_dir"],
        reports_dir=workspace / config["paths"]["reports_dir"],
        fps=config["encoding"]["fps"],
        codec=config["encoding"]["codec"],
        crf=config["encoding"]["crf"],
        preset=config["encoding"]["preset"],
        pixel_format=config["encoding"]["pixel_format"],
        output_extension=config["encoding"]["output_extension"],
    )
    nas_mount_point = _resolve_path(root_dir, config["nas"].get("mount_point"))
    nas = NASUploader(
        target_dir=_resolve_target_dir(root_dir, nas_mount_point, config["nas"]["target_dir"]),
        mount_point=nas_mount_point,
        mount_script=_resolve_path(root_dir, config["nas"].get("mount_script")),
        unmount_script=_resolve_path(root_dir, config["nas"].get("unmount_script")),
        mount_method=config["nas"].get("mount_method", "fstab"),
        share=config["nas"].get("share"),
        protocol=config["nas"].get("protocol", "cifs"),
        credentials_file=_resolve_path(root_dir, config["nas"].get("credentials_file")),
        version=config["nas"].get("version"),
        mount_options=config["nas"].get("mount_options", []),
        use_sudo=bool(config["nas"].get("use_sudo", False)),
        use_rsync=bool(config["nas"].get("use_rsync", True)),
    )

    return AppContext(
        root_dir=workspace,
        config=config,
        state_db=state_db,
        wifi=wifi,
        client=client,
        sync_engine=sync_engine,
        sdcard_sync=sdcard_sync,
        encoder=encoder,
        nas=nas,
    )


def run_sync(context: AppContext, source_override: str | None = None) -> None:
    configured_source = context.config.get("sync", {}).get("source", "wifi")
    source = _normalize_sync_source(source_override or configured_source)
    logger.info("Starting sync run (source=%s)", source)

    if source == "wifi":
        context.wifi.connect_gopro()
        try:
            stats = context.sync_engine.sync_missing_files()
            logger.info("Sync stats: %s", stats)
        finally:
            context.wifi.disconnect(context.config["gopro"]["wifi_connection_name"])
            context.wifi.connect_home()
        logger.info("Sync run completed")
        return

    stats = context.sdcard_sync.sync_missing_files()
    logger.info("SD card sync stats: %s", stats)
    logger.info("Sync run completed")


def run_encode_upload(context: AppContext) -> None:
    logger.info("Starting encode/upload run")
    today = _current_capture_date(context.config)
    skip_current_day = context.config["encoding"].get("skip_current_day", True)
    min_frames = int(context.config["encoding"].get("min_frames_for_render", 300))

    for capture_date in context.state_db.iter_capture_dates_pending_render():
        if skip_current_day and capture_date >= today:
            continue
        frames = [record.path for record in context.state_db.list_day_media(capture_date) if record.path.exists()]
        if len(frames) < min_frames:
            logger.warning("Skipping %s; only %d frames", capture_date, len(frames))
            continue
        output_video, frame_count = context.encoder.render_day(capture_date, frame_paths=frames)
        context.state_db.mark_rendered(capture_date, str(output_video), frame_count)

        if context.config["nas"].get("enabled", True) and not context.state_db.is_uploaded(capture_date):
            context.wifi.connect_home()
            context.nas.mount()
            try:
                uploaded_path = context.nas.upload_file(output_video)
                report_path = (context.root_dir / context.config["paths"]["reports_dir"] / f"{capture_date}.txt")
                if report_path.exists():
                    context.nas.upload_file(report_path)
                context.state_db.mark_uploaded(capture_date, str(uploaded_path))
            finally:
                context.nas.unmount()
    logger.info("Encode/upload run completed")


def run_healthcheck(context: AppContext) -> None:
    sync_source = _normalize_sync_source(context.config.get("sync", {}).get("source", "wifi"))
    required_commands = ["nmcli", "ffmpeg"]
    if context.config["nas"].get("enabled", True):
        required_commands.append("rsync" if context.config["nas"].get("use_rsync", True) else "cp")
        required_commands.append("mountpoint")
        required_commands.extend(["mount", "umount"])

    missing = [command for command in required_commands if shutil.which(command) is None]
    if missing:
        raise RuntimeError(f"Missing required commands: {', '.join(sorted(missing))}")

    connections = set(context.wifi.list_connections())
    if sync_source == "wifi" and context.wifi.gopro_connection not in connections:
        raise RuntimeError(
            f"GoPro NetworkManager connection not found: {context.wifi.gopro_connection}"
        )
    should_require_home_connection = bool(context.config["nas"].get("enabled", True)) or sync_source == "wifi"
    if (
        should_require_home_connection
        and context.wifi.home_connection
        and context.wifi.home_connection not in connections
    ):
        raise RuntimeError(
            f"Home NetworkManager connection not found: {context.wifi.home_connection}"
        )

    if sync_source == "sdcard" and not context.config.get("sdcard", {}).get("source_dir"):
        raise RuntimeError("sdcard.source_dir is required when sync.source is sdcard")

    if context.config["nas"].get("enabled", True):
        mount_method = context.config["nas"].get("mount_method", "fstab")
        if mount_method == "cifs" and not context.config["nas"].get("share"):
            raise RuntimeError("nas.share is required when nas.mount_method is cifs")
        if context.nas.credentials_file and not context.nas.credentials_file.exists():
            raise RuntimeError(f"NAS credentials file not found: {context.nas.credentials_file}")
        if context.nas.mount_point:
            mount_parent = context.nas.mount_point.parent
            if not context.nas.mount_point.exists() and not os.access(mount_parent, os.W_OK) and not context.nas.use_sudo:
                raise RuntimeError(
                    f"Cannot create NAS mount point without elevated permissions: {context.nas.mount_point}. "
                    "Either create it first or set nas.use_sudo: true."
                )

    (context.root_dir / context.config["paths"]["raw_dir"]).mkdir(parents=True, exist_ok=True)
    (context.root_dir / context.config["paths"]["indexed_dir"]).mkdir(parents=True, exist_ok=True)
    (context.root_dir / context.config["paths"]["renders_dir"]).mkdir(parents=True, exist_ok=True)
    (context.root_dir / context.config["paths"]["reports_dir"]).mkdir(parents=True, exist_ok=True)
    (context.root_dir / context.config["paths"]["logs_dir"]).mkdir(parents=True, exist_ok=True)
    logger.info("Workspace: %s", context.root_dir)
    logger.info("Healthcheck OK")


def run_mount_nas(context: AppContext) -> None:
    logger.info("Mounting NAS")
    context.nas.mount_direct()
    logger.info("NAS mounted")


def run_unmount_nas(context: AppContext) -> None:
    logger.info("Unmounting NAS")
    context.nas.unmount_direct()
    logger.info("NAS unmounted")
