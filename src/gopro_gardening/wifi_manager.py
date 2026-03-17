from __future__ import annotations

import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class WifiManager:
    def __init__(self, gopro_connection: str, home_connection: Optional[str] = None) -> None:
        self.gopro_connection = gopro_connection
        self.home_connection = home_connection

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        logger.info("Running command: %s", " ".join(args))
        return subprocess.run(args, check=check, text=True, capture_output=True)

    def connect_gopro(self) -> None:
        self._run("nmcli", "connection", "up", self.gopro_connection)
        logger.info("Connected to GoPro Wi-Fi: %s", self.gopro_connection)

    def connect_home(self) -> None:
        if not self.home_connection:
            logger.info("No home Wi-Fi connection configured; skipping reconnect")
            return
        self._run("nmcli", "connection", "up", self.home_connection)
        logger.info("Connected to home Wi-Fi: %s", self.home_connection)

    def disconnect(self, connection_name: Optional[str] = None) -> None:
        if connection_name:
            self._run("nmcli", "connection", "down", connection_name, check=False)
            logger.info("Disconnected: %s", connection_name)
            return
        for name in (self.gopro_connection, self.home_connection):
            if not name:
                continue
            self._run("nmcli", "connection", "down", name, check=False)
