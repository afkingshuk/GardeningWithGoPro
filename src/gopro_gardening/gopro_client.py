from __future__ import annotations

import logging
from typing import Iterable, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class GoProClient:
    def __init__(self, base_url: str, timeout: int = 30, user_agent: str = "gopro-gardening-pipeline/0.1") -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.timeout = timeout

    def _get_links(self, url: str) -> List[str]:
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        return [a.get("href") for a in soup.find_all("a", href=True)]

    def list_media_dirs(self) -> List[str]:
        links = self._get_links(self.base_url)
        dirs = [x for x in links if x and x.endswith("/") and len(x) == 9 and x[:3].isdigit() and x[3:8] == "GOPRO"]
        logger.info("Found media dirs: %s", dirs)
        return sorted(dirs)

    def list_files(self, media_dir: str) -> List[str]:
        url = urljoin(self.base_url, media_dir)
        links = self._get_links(url)
        files = [x for x in links if x and not x.endswith("/")]
        return sorted(files)

    def download_stream(self, media_dir: str, filename: str) -> Iterable[bytes]:
        file_url = urljoin(urljoin(self.base_url, media_dir), filename)
        logger.info("Downloading %s", file_url)
        with self.session.get(file_url, stream=True, timeout=self.timeout) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    yield chunk
