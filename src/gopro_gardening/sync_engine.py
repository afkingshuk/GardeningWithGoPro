from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from .gopro_client import DownloadValidationError, GoProClient, RemoteMediaFile
from .metadata import extract_capture_datetime
from .organizer import organize_by_capture_date
from .state_db import StateDB

logger = logging.getLogger(__name__)


class SyncEngine:
    def __init__(
        self,
        client: GoProClient,
        state_db: StateDB,
        raw_dir: Path,
        indexed_dir: Path,
        media_extensions: List[str],
        timezone_name: str,
        stable_file_min_age_seconds: int = 0,
        retry_failed_downloads: bool = True,
        max_retries: int = 3,
    ) -> None:
        self.client = client
        self.state_db = state_db
        self.raw_dir = raw_dir
        self.indexed_dir = indexed_dir
        self.media_extensions = tuple(x.lower() for x in media_extensions)
        self.timezone_name = timezone_name
        self.stable_file_min_age_seconds = max(0, stable_file_min_age_seconds)
        self.retry_failed_downloads = retry_failed_downloads
        self.max_retries = max(1, max_retries)

    def _is_stable_remote_file(self, remote_file: RemoteMediaFile) -> bool:
        file_timestamp = remote_file.modified_at or remote_file.created_at
        if not file_timestamp or self.stable_file_min_age_seconds <= 0:
            return True
        age_seconds = (datetime.now(timezone.utc) - file_timestamp.astimezone(timezone.utc)).total_seconds()
        return age_seconds >= self.stable_file_min_age_seconds

    def _download_attempts(self) -> int:
        if not self.retry_failed_downloads:
            return 1
        return self.max_retries

    def _download_and_record(self, remote_file: RemoteMediaFile, final_path: Path) -> None:
        download_result = self.client.download_file(remote_file, final_path)

        capture_dt, _source = extract_capture_datetime(final_path, self.timezone_name)
        capture_ts = capture_dt.isoformat() if capture_dt else None
        capture_date = capture_dt.date().isoformat() if capture_dt else None
        indexed_path = None
        if capture_date:
            indexed_path = organize_by_capture_date(final_path, self.indexed_dir, capture_date)

        self.state_db.record_download(
            media_dir=remote_file.media_dir.rstrip("/"),
            filename=remote_file.filename,
            local_path=str(final_path),
            indexed_path=str(indexed_path) if indexed_path else None,
            size_bytes=download_result.size_bytes,
            capture_ts=capture_ts,
            capture_date=capture_date,
        )
        logger.info("Downloaded new file: %s", final_path)

    def sync_missing_files(self) -> Dict[str, int]:
        downloaded = 0
        skipped = 0
        unstable = 0
        failed = 0

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.indexed_dir.mkdir(parents=True, exist_ok=True)

        for remote_file in self.client.list_media_files():
            if not remote_file.filename.lower().endswith(self.media_extensions):
                continue
            if self.state_db.has_downloaded(remote_file.media_dir.rstrip("/"), remote_file.filename):
                skipped += 1
                continue
            if not self._is_stable_remote_file(remote_file):
                unstable += 1
                logger.info(
                    "Skipping unstable file for now: %s/%s",
                    remote_file.media_dir,
                    remote_file.filename,
                )
                continue

            media_dir_local = self.raw_dir / remote_file.media_dir.rstrip("/")
            media_dir_local.mkdir(parents=True, exist_ok=True)
            final_path = media_dir_local / remote_file.filename

            attempts = self._download_attempts()
            for attempt in range(1, attempts + 1):
                try:
                    self._download_and_record(remote_file, final_path)
                    downloaded += 1
                    break
                except DownloadValidationError as exc:
                    logger.warning(
                        "Integrity check failed for %s/%s on attempt %d/%d: %s",
                        remote_file.media_dir,
                        remote_file.filename,
                        attempt,
                        attempts,
                        exc,
                    )
                except Exception as exc:
                    logger.warning(
                        "Download failed for %s/%s on attempt %d/%d: %s",
                        remote_file.media_dir,
                        remote_file.filename,
                        attempt,
                        attempts,
                        exc,
                    )
                if attempt == attempts:
                    failed += 1

        return {
            "downloaded": downloaded,
            "skipped": skipped,
            "unstable": unstable,
            "failed": failed,
        }
