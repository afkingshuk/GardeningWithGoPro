from __future__ import annotations

from dataclasses import dataclass
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List

from .metadata import extract_capture_datetime
from .organizer import organize_by_capture_date
from .state_db import StateDB

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SDCardWorkItem:
    source_path: Path
    target_path: Path
    media_dir: str
    filename: str
    source_size: int
    db_size: int | None
    copy_required: bool


class SDCardSyncEngine:
    def __init__(
        self,
        state_db: StateDB,
        source_dir: Path | None,
        raw_dir: Path,
        indexed_dir: Path,
        media_extensions: List[str],
        timezone_name: str,
        estimated_copy_speed_mb_per_sec: float = 25.0,
        show_progress: bool = True,
    ) -> None:
        self.state_db = state_db
        self.source_dir = source_dir
        self.raw_dir = raw_dir
        self.indexed_dir = indexed_dir
        self.media_extensions = tuple(extension.lower() for extension in media_extensions)
        self.timezone_name = timezone_name
        self.estimated_copy_speed_mb_per_sec = max(1.0, float(estimated_copy_speed_mb_per_sec))
        self.show_progress = bool(show_progress)

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

    @staticmethod
    def _format_seconds(value: float | None) -> str:
        if value is None:
            return "--:--"
        total = max(0, int(value))
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        if hours > 0:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _print_progress(
        self,
        processed: int,
        total: int,
        copied_bytes: int,
        copyable_bytes: int,
        started_at: float,
    ) -> None:
        if total <= 0:
            return
        elapsed = max(0.001, time.monotonic() - started_at)
        progress = processed / total
        bar_width = 24
        filled = int(progress * bar_width)
        bar = "#" * filled + "-" * (bar_width - filled)
        items_rate = processed / elapsed
        eta_seconds = (total - processed) / items_rate if items_rate > 0 else None
        copied_mb = copied_bytes / (1024 * 1024)
        copyable_mb = copyable_bytes / (1024 * 1024)
        line = (
            f"[{bar}] {processed}/{total} {progress * 100:5.1f}% "
            f"| copy {copied_mb:8.1f}/{copyable_mb:8.1f} MB "
            f"| {items_rate:5.1f} files/s | eta {self._format_seconds(eta_seconds)}"
        )

        if self.show_progress and sys.stdout.isatty():
            sys.stdout.write("\r" + line.ljust(140))
            sys.stdout.flush()
            if processed == total:
                sys.stdout.write("\n")
                sys.stdout.flush()
            return

        if processed == total or processed % 200 == 0:
            logger.info("SD progress: %s", line)

    def _collect_work_items(self, dcim_dir: Path) -> tuple[list[SDCardWorkItem], Dict[str, int], int]:
        work_items: list[SDCardWorkItem] = []
        remote_total = 0
        eligible_total = 0
        skipped = 0
        ignored_extension = 0
        copyable_total = 0
        copyable_bytes = 0

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
            source_size = source_path.stat().st_size
            target_dir = self.raw_dir / media_dir if media_dir else self.raw_dir
            target_path = target_dir / filename
            target_size = target_path.stat().st_size if target_path.exists() else None
            db_size = self.state_db.get_download_size(media_dir, filename)

            is_up_to_date = db_size is not None and db_size == source_size and target_size == source_size
            if is_up_to_date:
                skipped += 1
                continue

            copy_required = target_size != source_size
            if copy_required:
                copyable_total += 1
                copyable_bytes += source_size
            work_items.append(
                SDCardWorkItem(
                    source_path=source_path,
                    target_path=target_path,
                    media_dir=media_dir,
                    filename=filename,
                    source_size=source_size,
                    db_size=db_size,
                    copy_required=copy_required,
                )
            )

        pre_counts = {
            "remote_total": remote_total,
            "eligible_total": eligible_total,
            "skipped": skipped,
            "ignored_extension": ignored_extension,
            "actionable_total": len(work_items),
            "copyable_total": copyable_total,
        }
        return work_items, pre_counts, copyable_bytes

    def sync_missing_files(self) -> Dict[str, int]:
        dcim_dir = self._resolve_dcim_dir()
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.indexed_dir.mkdir(parents=True, exist_ok=True)

        work_items, pre_counts, copyable_bytes = self._collect_work_items(dcim_dir)
        estimated_seconds = copyable_bytes / (self.estimated_copy_speed_mb_per_sec * 1024 * 1024)

        logger.info(
            "SD pre-scan from %s: remote_total=%d eligible_total=%d actionable_total=%d copyable_total=%d "
            "skipped=%d ignored_extension=%d est_copy_time=%s",
            dcim_dir,
            pre_counts["remote_total"],
            pre_counts["eligible_total"],
            pre_counts["actionable_total"],
            pre_counts["copyable_total"],
            pre_counts["skipped"],
            pre_counts["ignored_extension"],
            self._format_seconds(estimated_seconds),
        )

        downloaded = 0
        failed = 0
        registered_existing = 0
        updated = 0
        copied_bytes = 0
        processed = 0
        started_at = time.monotonic()

        for item in work_items:
            try:
                copied = False
                item.target_path.parent.mkdir(parents=True, exist_ok=True)
                if item.copy_required:
                    shutil.copy2(item.source_path, item.target_path)
                    copied = True
                    copied_bytes += item.source_size

                size_bytes = item.target_path.stat().st_size
                capture_dt, _source = extract_capture_datetime(item.target_path, self.timezone_name)
                capture_ts = capture_dt.isoformat() if capture_dt else None
                capture_date = capture_dt.date().isoformat() if capture_dt else None
                indexed_path = None
                if capture_date:
                    indexed_path = organize_by_capture_date(item.target_path, self.indexed_dir, capture_date)

                self.state_db.record_download(
                    media_dir=item.media_dir,
                    filename=item.filename,
                    local_path=str(item.target_path),
                    indexed_path=str(indexed_path) if indexed_path else None,
                    size_bytes=size_bytes,
                    capture_ts=capture_ts,
                    capture_date=capture_date,
                )

                if copied:
                    downloaded += 1
                    logger.debug("Imported from SD card: %s -> %s", item.source_path, item.target_path)
                else:
                    registered_existing += 1
                    logger.debug("Registered existing raw file in state DB: %s", item.target_path)
                if item.db_size is not None and item.db_size != item.source_size:
                    updated += 1
            except Exception as exc:
                failed += 1
                logger.warning("Failed importing %s/%s from SD card: %s", item.media_dir, item.filename, exc)
            finally:
                processed += 1
                self._print_progress(
                    processed=processed,
                    total=pre_counts["actionable_total"],
                    copied_bytes=copied_bytes,
                    copyable_bytes=copyable_bytes,
                    started_at=started_at,
                )

        logger.info("SD card import scan complete from %s", dcim_dir)
        return {
            "remote_total": pre_counts["remote_total"],
            "eligible_total": pre_counts["eligible_total"],
            "downloaded": downloaded,
            "registered_existing": registered_existing,
            "updated": updated,
            "skipped": pre_counts["skipped"],
            "failed": failed,
            "ignored_extension": pre_counts["ignored_extension"],
            "actionable_total": pre_counts["actionable_total"],
            "copyable_total": pre_counts["copyable_total"],
            "estimated_copy_seconds": int(estimated_seconds),
        }
