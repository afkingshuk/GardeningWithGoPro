from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS downloaded_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_dir TEXT NOT NULL,
    filename TEXT NOT NULL,
    local_path TEXT NOT NULL,
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


class StateDB:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

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
        size_bytes: int,
        capture_ts: Optional[str],
        capture_date: Optional[str],
    ) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO downloaded_files
            (media_dir, filename, local_path, size_bytes, capture_ts, capture_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (media_dir, filename, local_path, size_bytes, capture_ts, capture_date),
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
