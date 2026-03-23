from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Dict, List

from .metadata import extract_capture_datetime
from .organizer import organize_by_capture_date
from .state_db import StateDB

logger = logging.getLogger(__name__)


class SDCardSyncEngine:
    def __init__(
        self,
        state_db: StateDB,
        source_dir: Path | None,
        raw_dir: Path,
        indexed_dir: Path,
        media_extensions: List[str],
        timezone_name: str,
    ) -> None:
        self.state_db = state_db
        self.source_dir = source_dir
        self.raw_dir = raw_dir
        self.indexed_dir = indexed_dir
        self.media_extensions = tuple(extension.lower() for extension in media_extensions)
        self.timezone_name = timezone_name

    def _resolve_dcim_dir(self) -> Path:
        if self.source_dir is None:
            raise ValueError("sdcard.source_dir is not configured")
        source = self.source_dir.expanduser()
        if source.name.lower() == "dcim" and source.is_dir():
            return source
        if source.is_dir():
            direct = source / "DCIM"
            if direct.is_dir():
                return direct
            for child in source.iterdir():
                if child.is_dir() and child.name.lower() == "dcim":
                    return child
        raise FileNotFoundError(f"Could not find DCIM directory at or under: {source}")

    @staticmethod
    def _relative_media_dir(dcim_dir: Path, source_path: Path) -> str:
        parent = source_path.relative_to(dcim_dir).parent
        if str(parent) == ".":
            return ""
        return parent.as_posix().rstrip("/")

    def sync_missing_files(self) -> Dict[str, int]:
        dcim_dir = self._resolve_dcim_dir()
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.indexed_dir.mkdir(parents=True, exist_ok=True)

        remote_total = 0
        eligible_total = 0
        downloaded = 0
        skipped = 0
        failed = 0
        ignored_extension = 0
        registered_existing = 0

        for source_path in sorted(dcim_dir.rglob("*")):
            if not source_path.is_file():
                continue

            remote_total += 1
            filename = source_path.name
            if not filename.lower().endswith(self.media_extensions):
                ignored_extension += 1
                continue
            eligible_total += 1

            media_dir = self._relative_media_dir(dcim_dir, source_path)
            if self.state_db.has_downloaded(media_dir, filename):
                skipped += 1
                continue

            target_dir = self.raw_dir / media_dir if media_dir else self.raw_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / filename

            try:
                copied = False
                source_size = source_path.stat().st_size
                if not target_path.exists():
                    shutil.copy2(source_path, target_path)
                    copied = True
                elif target_path.stat().st_size != source_size:
                    shutil.copy2(source_path, target_path)
                    copied = True

                size_bytes = target_path.stat().st_size
                capture_dt, _source = extract_capture_datetime(target_path, self.timezone_name)
                capture_ts = capture_dt.isoformat() if capture_dt else None
                capture_date = capture_dt.date().isoformat() if capture_dt else None
                indexed_path = None
                if capture_date:
                    indexed_path = organize_by_capture_date(target_path, self.indexed_dir, capture_date)

                self.state_db.record_download(
                    media_dir=media_dir,
                    filename=filename,
                    local_path=str(target_path),
                    indexed_path=str(indexed_path) if indexed_path else None,
                    size_bytes=size_bytes,
                    capture_ts=capture_ts,
                    capture_date=capture_date,
                )

                if copied:
                    downloaded += 1
                    logger.info("Imported from SD card: %s -> %s", source_path, target_path)
                else:
                    registered_existing += 1
                    logger.info("Registered existing raw file in state DB: %s", target_path)
            except Exception as exc:
                failed += 1
                logger.warning("Failed importing %s/%s from SD card: %s", media_dir, filename, exc)

        logger.info("SD card import scan complete from %s", dcim_dir)
        return {
            "remote_total": remote_total,
            "eligible_total": eligible_total,
            "downloaded": downloaded,
            "registered_existing": registered_existing,
            "skipped": skipped,
            "failed": failed,
            "ignored_extension": ignored_extension,
        }
