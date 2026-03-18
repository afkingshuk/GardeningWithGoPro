from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS downloaded_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_dir TEXT NOT NULL,
    filename TEXT NOT NULL,
    local_path TEXT NOT NULL,
    indexed_path TEXT,
    size_bytes INTEGER,
    capture_ts TEXT,
    capture_date TEXT,
    downloaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(media_dir, filename)
);

CREATE TABLE IF NOT EXISTS rendered_days (
    capture_date TEXT PRIMARY KEY,
    video_path TEXT NOT NULL,
    frame_count INTEGER,
    rendered_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS uploaded_days (
    capture_date TEXT PRIMARY KEY,
    target_path TEXT NOT NULL,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass(frozen=True)
class DayMediaRecord:
    filename: str
    path: Path
    capture_ts: datetime | None


class StateDB:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(SCHEMA)
        self._ensure_downloaded_file_columns()
        self.conn.commit()

    def _ensure_downloaded_file_columns(self) -> None:
        columns = {
            row[1]
            for row in self.conn.execute("PRAGMA table_info(downloaded_files)").fetchall()
        }
        if "indexed_path" not in columns:
            self.conn.execute("ALTER TABLE downloaded_files ADD COLUMN indexed_path TEXT")

    @staticmethod
    def _parse_capture_ts(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def has_downloaded(self, media_dir: str, filename: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM downloaded_files WHERE media_dir = ? AND filename = ? LIMIT 1",
            (media_dir, filename),
        )
        return cur.fetchone() is not None

    def record_download(
        self,
        media_dir: str,
        filename: str,
        local_path: str,
        indexed_path: Optional[str],
        size_bytes: int,
        capture_ts: Optional[str],
        capture_date: Optional[str],
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO downloaded_files
            (media_dir, filename, local_path, indexed_path, size_bytes, capture_ts, capture_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (media_dir, filename, local_path, indexed_path, size_bytes, capture_ts, capture_date),
        )
        self.conn.commit()

    def iter_capture_dates_pending_render(self) -> Iterable[str]:
        cur = self.conn.execute(
            """
            SELECT DISTINCT capture_date
            FROM downloaded_files
            WHERE capture_date IS NOT NULL
              AND capture_date NOT IN (SELECT capture_date FROM rendered_days)
            ORDER BY capture_date
            """
        )
        for row in cur.fetchall():
            yield row[0]

    def mark_rendered(self, capture_date: str, video_path: str, frame_count: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO rendered_days (capture_date, video_path, frame_count) VALUES (?, ?, ?)",
            (capture_date, video_path, frame_count),
        )
        self.conn.commit()

    def is_uploaded(self, capture_date: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM uploaded_days WHERE capture_date = ? LIMIT 1", (capture_date,))
        return cur.fetchone() is not None

    def mark_uploaded(self, capture_date: str, target_path: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO uploaded_days (capture_date, target_path) VALUES (?, ?)",
            (capture_date, target_path),
        )
        self.conn.commit()

    def list_day_media(self, capture_date: str) -> list[DayMediaRecord]:
        cur = self.conn.execute(
            """
            SELECT filename, COALESCE(indexed_path, local_path), capture_ts
            FROM downloaded_files
            WHERE capture_date = ?
            """,
            (capture_date,),
        )
        records = [
            DayMediaRecord(
                filename=row[0],
                path=Path(row[1]),
                capture_ts=self._parse_capture_ts(row[2]),
            )
            for row in cur.fetchall()
        ]
        return sorted(
            records,
            key=lambda record: (
                record.capture_ts is None,
                (
                    record.capture_ts.astimezone(timezone.utc).isoformat()
                    if record.capture_ts and record.capture_ts.tzinfo
                    else record.capture_ts.isoformat()
                    if record.capture_ts
                    else ""
                ),
                record.filename,
            ),
        )
