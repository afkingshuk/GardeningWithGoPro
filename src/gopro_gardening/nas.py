from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class NASUploader:
    def __init__(
        self,
        target_dir: Path,
        mount_point: Path | None = None,
        mount_script: Path | None = None,
        unmount_script: Path | None = None,
    ) -> None:
        self.target_dir = target_dir
        self.mount_point = mount_point
        self.mount_script = mount_script
        self.unmount_script = unmount_script

    def _is_mounted(self) -> bool:
        if not self.mount_point:
            return True
        result = subprocess.run(
            ["mountpoint", "-q", str(self.mount_point)],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _require_mounted(self) -> None:
        if self.mount_point and not self._is_mounted():
            raise RuntimeError(f"NAS mount point is not mounted: {self.mount_point}")

    def mount(self) -> None:
        if self.mount_script and self.mount_script.exists():
            subprocess.run(["bash", str(self.mount_script)], check=True)
        self._require_mounted()

    def unmount(self) -> None:
        if self.unmount_script and self.unmount_script.exists():
            subprocess.run(["bash", str(self.unmount_script)], check=True)

    def upload_file(self, src: Path) -> Path:
        self._require_mounted()
        self.target_dir.mkdir(parents=True, exist_ok=True)
        dst = self.target_dir / src.name
        logger.info("Uploading %s -> %s", src, dst)
        subprocess.run(["rsync", "-av", str(src), str(dst)], check=True)
        return dst
