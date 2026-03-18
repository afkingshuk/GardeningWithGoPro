from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RemoteMediaFile:
    media_dir: str
    filename: str
    size_bytes: int | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None


@dataclass(frozen=True)
class DownloadResult:
    size_bytes: int
    file_timestamp: datetime | None = None


class DownloadValidationError(RuntimeError):
    pass


class GoProClient:
    def __init__(self, base_url: str, timeout: int = 30, user_agent: str = "gopro-gardening-pipeline/0.1") -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.timeout = timeout

    def _api_root(self) -> str:
        parts = urlsplit(self.base_url)
        return f"{parts.scheme}://{parts.netloc}/"

    def _media_list_endpoints(self) -> list[str]:
        api_root = self._api_root()
        return [
            urljoin(api_root, "gopro/media/list"),
            urljoin(api_root, "gp/gpMediaList"),
        ]

    @staticmethod
    def _parse_int(value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_epoch(value: object) -> datetime | None:
        parsed = GoProClient._parse_int(value)
        if parsed is None:
            return None
        return datetime.fromtimestamp(parsed, tz=timezone.utc)

    @staticmethod
    def _parse_content_range_total(value: str | None) -> int | None:
        if not value or "/" not in value:
            return None
        return GoProClient._parse_int(value.rsplit("/", 1)[1])

    def _parse_media_list_payload(self, payload: object) -> list[RemoteMediaFile]:
        if not isinstance(payload, dict):
            return []

        media_entries = payload.get("media")
        if not isinstance(media_entries, list):
            return []

        files: list[RemoteMediaFile] = []
        for media_entry in media_entries:
            if not isinstance(media_entry, dict):
                continue

            media_dir = str(media_entry.get("d", "")).strip().rstrip("/")
            if not media_dir:
                continue

            for file_entry in media_entry.get("fs", []) or []:
                if not isinstance(file_entry, dict):
                    continue
                filename = str(file_entry.get("n", "")).strip()
                if not filename:
                    continue
                files.append(
                    RemoteMediaFile(
                        media_dir=media_dir,
                        filename=filename,
                        size_bytes=self._parse_int(file_entry.get("s")),
                        created_at=self._parse_epoch(file_entry.get("cre")),
                        modified_at=self._parse_epoch(file_entry.get("mod")),
                    )
                )
        return sorted(files, key=lambda item: (item.media_dir, item.filename))

    def _get_links(self, url: str) -> List[str]:
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        return [a.get("href") for a in soup.find_all("a", href=True)]

    def _list_media_files_via_api(self) -> list[RemoteMediaFile]:
        last_error: Exception | None = None
        for endpoint in self._media_list_endpoints():
            try:
                response = self.session.get(endpoint, timeout=self.timeout)
                response.raise_for_status()
                files = self._parse_media_list_payload(response.json())
                if files:
                    logger.info("Loaded %d media files from %s", len(files), endpoint)
                    return files
            except Exception as exc:
                last_error = exc
                logger.debug("Media list endpoint failed: %s", endpoint, exc_info=exc)

        if last_error:
            logger.info("Falling back to HTML media listing after API failure: %s", last_error)
        return []

    def _list_media_files_via_html(self) -> list[RemoteMediaFile]:
        files: list[RemoteMediaFile] = []
        for media_dir in self.list_media_dirs():
            for filename in self.list_files(media_dir):
                files.append(RemoteMediaFile(media_dir=media_dir.rstrip("/"), filename=filename))
        return files

    def list_media_files(self) -> list[RemoteMediaFile]:
        files = self._list_media_files_via_api()
        if files:
            return files
        return self._list_media_files_via_html()

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

    def download_file(self, remote_file: RemoteMediaFile, destination: os.PathLike[str] | str) -> DownloadResult:
        media_dir = remote_file.media_dir.rstrip("/") + "/"
        file_url = urljoin(urljoin(self.base_url, media_dir), remote_file.filename)
        destination_path = os.fspath(destination)
        part_path = f"{destination_path}.part"
        existing_bytes = os.path.getsize(part_path) if os.path.exists(part_path) else 0
        if existing_bytes > 0 and remote_file.size_bytes is not None and existing_bytes == remote_file.size_bytes:
            os.replace(part_path, destination_path)
            file_timestamp = remote_file.created_at or remote_file.modified_at
            if file_timestamp is not None:
                ts = file_timestamp.timestamp()
                os.utime(destination_path, (ts, ts))
            return DownloadResult(size_bytes=existing_bytes, file_timestamp=file_timestamp)
        request_headers = {"Range": f"bytes={existing_bytes}-"} if existing_bytes > 0 else None
        logger.info("Downloading %s", file_url)
        with self.session.get(file_url, stream=True, timeout=self.timeout, headers=request_headers) as r:
            r.raise_for_status()
            append_mode = existing_bytes > 0 and r.status_code == 206
            if existing_bytes > 0 and not append_mode and os.path.exists(part_path):
                os.remove(part_path)
                existing_bytes = 0

            content_length = self._parse_int(r.headers.get("Content-Length"))
            response_total_size = None
            if append_mode:
                response_total_size = (
                    self._parse_content_range_total(r.headers.get("Content-Range"))
                    or (existing_bytes + content_length if content_length is not None else None)
                )
            else:
                response_total_size = content_length

            if (
                remote_file.size_bytes is not None
                and response_total_size is not None
                and remote_file.size_bytes != response_total_size
            ):
                logger.warning(
                    "Media-list size mismatch for %s/%s: api=%d http=%d; using HTTP size",
                    remote_file.media_dir,
                    remote_file.filename,
                    remote_file.size_bytes,
                    response_total_size,
                )

            expected_size = response_total_size if response_total_size is not None else remote_file.size_bytes
            header_timestamp = r.headers.get("Last-Modified")
            file_timestamp = remote_file.created_at or remote_file.modified_at
            if not file_timestamp and header_timestamp:
                try:
                    file_timestamp = parsedate_to_datetime(header_timestamp).astimezone(timezone.utc)
                except (TypeError, ValueError):
                    file_timestamp = None

            size_bytes = existing_bytes
            with open(part_path, "ab" if append_mode else "wb") as handle:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    size_bytes += len(chunk)
            if expected_size is not None and size_bytes != expected_size:
                if os.path.exists(part_path):
                    os.remove(part_path)
                raise DownloadValidationError(
                    f"Expected {expected_size} bytes for {remote_file.filename}, got {size_bytes}"
                )
            os.replace(part_path, destination_path)

        if file_timestamp is not None:
            ts = file_timestamp.timestamp()
            os.utime(destination_path, (ts, ts))

        return DownloadResult(size_bytes=size_bytes, file_timestamp=file_timestamp)
