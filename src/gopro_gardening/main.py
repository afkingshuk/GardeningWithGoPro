from __future__ import annotations

import logging
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
    encoder: Encoder
    nas: NASUploader


def _resolve_path(base_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
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
    nas = NASUploader(
        target_dir=Path(config["nas"]["target_dir"]).expanduser(),
        mount_point=_resolve_path(root_dir, config["nas"].get("mount_point")),
        mount_script=_resolve_path(root_dir, config["nas"].get("mount_script")),
        unmount_script=_resolve_path(root_dir, config["nas"].get("unmount_script")),
    )

    return AppContext(
        root_dir=workspace,
        config=config,
        state_db=state_db,
        wifi=wifi,
        client=client,
        sync_engine=sync_engine,
        encoder=encoder,
        nas=nas,
    )


def run_sync(context: AppContext) -> None:
    logger.info("Starting sync run")
    context.wifi.connect_gopro()
    try:
        stats = context.sync_engine.sync_missing_files()
        logger.info("Sync stats: %s", stats)
    finally:
        context.wifi.disconnect(context.config["gopro"]["wifi_connection_name"])
        context.wifi.connect_home()
    logger.info("Sync run completed")


def run_encode_upload(context: AppContext) -> None:
    logger.info("Starting encode/upload run")
    today = _current_capture_date(context.config)
    skip_current_day = context.config["encoding"].get("skip_current_day", True)
    min_frames = int(context.config["encoding"].get("min_frames_for_render", 300))

    for capture_date in context.state_db.iter_capture_dates_pending_render():
        if skip_current_day and capture_date >= today:
            continue
        frames = context.encoder.get_frame_paths(capture_date)
        if len(frames) < min_frames:
            logger.warning("Skipping %s; only %d frames", capture_date, len(frames))
            continue
        output_video, frame_count = context.encoder.render_day(capture_date)
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
    logger.info("Healthcheck OK")
    logger.info("Workspace: %s", context.root_dir)
