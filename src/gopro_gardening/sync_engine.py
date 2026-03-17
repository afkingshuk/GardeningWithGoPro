from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .gopro_client import GoProClient
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
    ) -> None:
        self.client = client
        self.state_db = state_db
        self.raw_dir = raw_dir
        self.indexed_dir = indexed_dir
        self.media_extensions = tuple(x.lower() for x in media_extensions)

    def sync_missing_files(self) -> Dict[str, int]:
        downloaded = 0
        skipped = 0

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.indexed_dir.mkdir(parents=True, exist_ok=True)

        for media_dir in self.client.list_media_dirs():
            media_dir_local = self.raw_dir / media_dir.rstrip("/")
            media_dir_local.mkdir(parents=True, exist_ok=True)

            for filename in self.client.list_files(media_dir):
                if not filename.lower().endswith(self.media_extensions):
                    continue
                if self.state_db.has_downloaded(media_dir.rstrip("/"), filename):
                    skipped += 1
                    continue

                final_path = media_dir_local / filename
                temp_path = final_path.with_suffix(final_path.suffix + ".part")
                size_bytes = 0
                for chunk in self.client.download_stream(media_dir, filename):
                    with temp_path.open("ab") as f:
                        f.write(chunk)
                        size_bytes += len(chunk)
                temp_path.replace(final_path)

                capture_dt, _source = extract_capture_datetime(final_path)
                capture_ts = capture_dt.isoformat() if capture_dt else None
                capture_date = capture_dt.date().isoformat() if capture_dt else None
                if capture_date:
                    organize_by_capture_date(final_path, self.indexed_dir, capture_date)

                self.state_db.record_download(
                    media_dir=media_dir.rstrip("/"),
                    filename=filename,
                    local_path=str(final_path),
                    size_bytes=size_bytes,
                    capture_ts=capture_ts,
                    capture_date=capture_date,
                )
                downloaded += 1
                logger.info("Downloaded new file: %s", final_path)

        return {"downloaded": downloaded, "skipped": skipped}
