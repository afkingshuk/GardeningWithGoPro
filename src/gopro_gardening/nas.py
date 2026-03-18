from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


class NASUploader:
    def __init__(
        self,
        target_dir: Path,
        mount_point: Path | None = None,
        mount_script: Path | None = None,
        unmount_script: Path | None = None,
        mount_method: str = "fstab",
        share: str | None = None,
        protocol: str = "cifs",
        credentials_file: Path | None = None,
        version: str | None = None,
        mount_options: Sequence[str] | None = None,
        use_sudo: bool = False,
        use_rsync: bool = True,
    ) -> None:
        self.target_dir = target_dir
        self.mount_point = mount_point
        self.mount_script = mount_script
        self.unmount_script = unmount_script
        self.mount_method = mount_method
        self.share = share
        self.protocol = protocol
        self.credentials_file = credentials_file
        self.version = version
        self.mount_options = list(mount_options or [])
        self.use_sudo = use_sudo
        self.use_rsync = use_rsync

    def _wrap_command(self, cmd: list[str]) -> list[str]:
        if self.use_sudo:
            return ["sudo", "-n", *cmd]
        return cmd

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

    def _build_cifs_options(self) -> list[str]:
        options = list(self.mount_options)
        if self.credentials_file:
            options.append(f"credentials={self.credentials_file.expanduser()}")
        if self.version:
            options.append(f"vers={self.version}")
        if hasattr(os, "getuid") and hasattr(os, "getgid"):
            options.append(f"uid={os.getuid()}")
            options.append(f"gid={os.getgid()}")
        return options

    def mount_direct(self) -> None:
        if self._is_mounted():
            return
        if not self.mount_point:
            raise RuntimeError("NAS mount_point is required")

        self.mount_point.mkdir(parents=True, exist_ok=True)
        if self.mount_method == "fstab":
            cmd = ["mount", str(self.mount_point)]
        elif self.mount_method == "cifs":
            if not self.share:
                raise RuntimeError("NAS share is required for cifs mount_method")
            cmd = ["mount", "-t", self.protocol, self.share, str(self.mount_point)]
            options = self._build_cifs_options()
            if options:
                cmd.extend(["-o", ",".join(options)])
        else:
            raise RuntimeError(f"Unsupported nas.mount_method: {self.mount_method}")

        subprocess.run(self._wrap_command(cmd), check=True)
        self._require_mounted()

    def unmount_direct(self) -> None:
        if not self.mount_point or not self._is_mounted():
            return
        subprocess.run(self._wrap_command(["umount", str(self.mount_point)]), check=True)

    def mount(self) -> None:
        if self.mount_script and self.mount_script.exists():
            subprocess.run(["bash", str(self.mount_script)], check=True)
        else:
            self.mount_direct()
        self._require_mounted()

    def unmount(self) -> None:
        if self.unmount_script and self.unmount_script.exists():
            subprocess.run(["bash", str(self.unmount_script)], check=True)
        else:
            self.unmount_direct()

    def upload_file(self, src: Path) -> Path:
        self._require_mounted()
        self.target_dir.mkdir(parents=True, exist_ok=True)
        dst = self.target_dir / src.name
        logger.info("Uploading %s -> %s", src, dst)
        if self.use_rsync:
            subprocess.run(["rsync", "-av", str(src), str(dst)], check=True)
        else:
            subprocess.run(["cp", "-f", str(src), str(dst)], check=True)
        return dst
