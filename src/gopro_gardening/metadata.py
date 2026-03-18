from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image
from PIL.ExifTags import TAGS


EXIF_DATETIME_KEYS = {"DateTimeOriginal", "DateTimeDigitized", "DateTime"}


def _normalize_datetime(value: datetime, timezone_name: str | None) -> datetime:
    if not timezone_name:
        return value

    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid timezone: {timezone_name}") from exc

    if value.tzinfo is None:
        return value.replace(tzinfo=tzinfo)
    return value.astimezone(tzinfo)


def _parse_mtime(image_path: Path, timezone_name: str | None) -> datetime:
    if not timezone_name:
        return datetime.fromtimestamp(image_path.stat().st_mtime)

    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid timezone: {timezone_name}") from exc
    return datetime.fromtimestamp(image_path.stat().st_mtime, tz=tzinfo)


def extract_capture_datetime(image_path: Path, timezone_name: str | None = None) -> Tuple[Optional[datetime], str]:
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if exif:
                for key, value in exif.items():
                    tag_name = TAGS.get(key, str(key))
                    if tag_name in EXIF_DATETIME_KEYS and isinstance(value, str):
                        try:
                            parsed = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                            return _normalize_datetime(parsed, timezone_name), "exif"
                        except ValueError:
                            pass
    except Exception:
        pass

    return _parse_mtime(image_path, timezone_name), "mtime"
