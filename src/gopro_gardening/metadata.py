from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image
from PIL.ExifTags import TAGS


EXIF_DATETIME_KEYS = {"DateTimeOriginal", "DateTimeDigitized", "DateTime"}


def extract_capture_datetime(image_path: Path) -> Tuple[Optional[datetime], str]:
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if exif:
                for key, value in exif.items():
                    tag_name = TAGS.get(key, str(key))
                    if tag_name in EXIF_DATETIME_KEYS and isinstance(value, str):
                        try:
                            return datetime.strptime(value, "%Y:%m:%d %H:%M:%S"), "exif"
                        except ValueError:
                            pass
    except Exception:
        pass

    stat = image_path.stat()
    return datetime.fromtimestamp(stat.st_mtime), "mtime"
