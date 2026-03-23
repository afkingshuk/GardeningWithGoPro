from __future__ import annotations

from collections import deque
import logging
import os
import re
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


@dataclass(frozen=True)
class DirectoryListingEntry:
    href: str
    modified_at: datetime | None = None


class GoProClient:
    def __init__(self, base_url: str, timeout: int = 30, user_agent: str = "gopro-gardening-pipeline/0.1") -> None:
        self.base_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.timeout = timeout

    @staticmethod
    def _parse_int(value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_content_range_total(value: str | None) -> int | None:
        if not value or "/" not in value:
            return None
        return GoProClient._parse_int(value.rsplit("/", 1)[1])

    @staticmethod
    def _parse_listing_datetime(value: str) -> datetime | None:
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        for fmt in (
            "%d-%b-%Y %H:%M",
            "%d-%b-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                naive = datetime.strptime(value, fmt)
                return naive.replace(tzinfo=local_tz).astimezone(timezone.utc)
            except ValueError:
                continue
        return None

    @classmethod
    def _extract_modified_from_text(cls, text: str) -> datetime | None:
        text = " ".join(text.split())
        if not text:
            return None
        for pattern in (
            r"(\d{1,2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}(?::\d{2})?)",
            r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)",
        ):
            match = re.search(pattern, text)
            if not match:
                continue
            parsed = cls._parse_listing_datetime(match.group(1))
            if parsed is not None:
                return parsed
        return None

    def _get_directory_entries(self, url: str) -> List[DirectoryListingEntry]:
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        entries: list[DirectoryListingEntry] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href")
            if not href:
                continue

            modified_at: datetime | None = None
            parent_row = anchor.find_parent("tr")
            if parent_row is not None:
                modified_at = self._extract_modified_from_text(parent_row.get_text(" ", strip=True))
            if modified_at is None and isinstance(anchor.next_sibling, str):
                modified_at = self._extract_modified_from_text(anchor.next_sibling)
            if modified_at is None and anchor.parent is not None:
                modified_at = self._extract_modified_from_text(anchor.parent.get_text(" ", strip=True))

            entries.append(DirectoryListingEntry(href=href, modified_at=modified_at))
        return entries

    def _get_links(self, url: str) -> List[str]:
        return [entry.href for entry in self._get_directory_entries(url)]

    @staticmethod
    def _normalize_dir_url(url: str) -> str:
        parts = urlsplit(url)
        path = parts.path if parts.path.endswith("/") else f"{parts.path}/"
        return parts._replace(path=path, query="", fragment="").geturl()

    def _is_within_base(self, url: str) -> bool:
        base = urlsplit(self.base_url)
        target = urlsplit(url)
        if (base.scheme, base.netloc) != (target.scheme, target.netloc):
            return False
        base_path = base.path if base.path.endswith("/") else f"{base.path}/"
        return target.path.startswith(base_path)

    def _build_remote_file(self, file_url: str, modified_at: datetime | None = None) -> RemoteMediaFile | None:
        base = urlsplit(self.base_url)
        target = urlsplit(file_url)
        base_path = base.path if base.path.endswith("/") else f"{base.path}/"
        if not target.path.startswith(base_path):
            return None

        relative_path = target.path[len(base_path):].lstrip("/")
        if not relative_path or relative_path.endswith("/"):
            return None

        parts = [piece for piece in relative_path.split("/") if piece]
        if not parts:
            return None

        filename = parts[-1]
        media_dir = "/".join(parts[:-1])
        return RemoteMediaFile(media_dir=media_dir, filename=filename, modified_at=modified_at)

    def _list_media_files_recursive_html(self) -> list[RemoteMediaFile]:
        start_url = self._normalize_dir_url(self.base_url)
        queue: deque[str] = deque([start_url])
        seen_dirs: set[str] = {start_url}
        files: dict[tuple[str, str], RemoteMediaFile] = {}

        while queue:
            current_dir = queue.popleft()
            try:
                entries = self._get_directory_entries(current_dir)
            except Exception as exc:
                logger.warning("Failed to list %s: %s", current_dir, exc)
                continue

            for entry in entries:
                href = entry.href
                if not href:
                    continue
                href = href.strip()
                if href in {"./", "../"}:
                    continue

                absolute_url = urljoin(current_dir, href)
                absolute_url = urlsplit(absolute_url)._replace(query="", fragment="").geturl()
                if not self._is_within_base(absolute_url):
                    continue

                if absolute_url.endswith("/"):
                    normalized = self._normalize_dir_url(absolute_url)
                    if normalized not in seen_dirs:
                        seen_dirs.add(normalized)
                        queue.append(normalized)
                    continue

                remote_file = self._build_remote_file(absolute_url, modified_at=entry.modified_at)
                if remote_file is None:
                    continue
                key = (remote_file.media_dir, remote_file.filename)
                existing = files.get(key)
                if existing is None or (existing.modified_at is None and remote_file.modified_at is not None):
                    files[key] = remote_file

        logger.info(
            "Discovered %d files across %d directories under %s",
            len(files),
            len(seen_dirs),
            self.base_url,
        )
        return sorted(files.values(), key=lambda item: (item.media_dir, item.filename))

    def list_media_files(self) -> list[RemoteMediaFile]:
        return self._list_media_files_recursive_html()

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
        if remote_file.media_dir:
            relative_path = f"{remote_file.media_dir.rstrip('/')}/{remote_file.filename}"
        else:
            relative_path = remote_file.filename
        file_url = urljoin(self.base_url, relative_path)
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
