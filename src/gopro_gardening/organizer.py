from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def organize_by_capture_date(src_path: Path, indexed_root: Path, capture_date: str) -> Path:
    day_dir = indexed_root / capture_date
    day_dir.mkdir(parents=True, exist_ok=True)
    target = day_dir / src_path.name
    if not target.exists():
        try:
            target.hardlink_to(src_path)
        except Exception:
            shutil.copy2(src_path, target)
        logger.info("Indexed %s -> %s", src_path, target)
    return target
