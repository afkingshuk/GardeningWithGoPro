from __future__ import annotations

from datetime import datetime, timezone

from gopro_gardening.gopro_client import DirectoryListingEntry, GoProClient


def test_list_media_files_recursively_from_dcim_html() -> None:
    client = GoProClient("http://10.5.5.9:8080/videos/DCIM/")
    modified = datetime(2026, 3, 23, 18, 41, tzinfo=timezone.utc)
    listing_map = {
        "http://10.5.5.9:8080/videos/DCIM/": [
            DirectoryListingEntry("./"),
            DirectoryListingEntry("../"),
            DirectoryListingEntry("100GOPRO/"),
            DirectoryListingEntry("101GOPRO/"),
            DirectoryListingEntry("ROOT.JPG"),
            DirectoryListingEntry("http://example.com/not-gopro/"),
        ],
        "http://10.5.5.9:8080/videos/DCIM/100GOPRO/": [
            DirectoryListingEntry("A001.JPG"),
            DirectoryListingEntry("A002.GPR"),
            DirectoryListingEntry("NESTED/"),
            DirectoryListingEntry("http://10.5.5.9:8080/videos/DCIM/100GOPRO/A001.JPG", modified_at=modified),
        ],
        "http://10.5.5.9:8080/videos/DCIM/100GOPRO/NESTED/": [
            DirectoryListingEntry("A003.JPG"),
            DirectoryListingEntry("../"),
        ],
        "http://10.5.5.9:8080/videos/DCIM/101GOPRO/": [
            DirectoryListingEntry("B001.JPG"),
        ],
    }

    def fake_get_directory_entries(url: str) -> list[DirectoryListingEntry]:
        return listing_map[url]

    client._get_directory_entries = fake_get_directory_entries  # type: ignore[method-assign]

    files = client.list_media_files()

    assert [(item.media_dir, item.filename) for item in files] == [
        ("", "ROOT.JPG"),
        ("100GOPRO", "A001.JPG"),
        ("100GOPRO", "A002.GPR"),
        ("100GOPRO/NESTED", "A003.JPG"),
        ("101GOPRO", "B001.JPG"),
    ]
    a001 = next(item for item in files if item.media_dir == "100GOPRO" and item.filename == "A001.JPG")
    assert a001.modified_at == modified


def test_recursive_listing_ignores_urls_outside_base_path() -> None:
    client = GoProClient("http://10.5.5.9:8080/videos/DCIM/")
    listing_map = {
        "http://10.5.5.9:8080/videos/DCIM/": [
            DirectoryListingEntry("100GOPRO/"),
            DirectoryListingEntry("/videos/OTHER/NOT_THIS.JPG"),
            DirectoryListingEntry("http://10.5.5.9:8080/videos/OTHER/NOPE.JPG"),
            DirectoryListingEntry("http://other-host.local/videos/DCIM/NOPE.JPG"),
        ],
        "http://10.5.5.9:8080/videos/DCIM/100GOPRO/": [
            DirectoryListingEntry("OK.JPG"),
        ],
    }

    def fake_get_directory_entries(url: str) -> list[DirectoryListingEntry]:
        return listing_map[url]

    client._get_directory_entries = fake_get_directory_entries  # type: ignore[method-assign]

    files = client.list_media_files()

    assert [(item.media_dir, item.filename) for item in files] == [
        ("100GOPRO", "OK.JPG"),
    ]


def test_extract_modified_from_index_text() -> None:
    parsed = GoProClient._extract_modified_from_text("GPA0001.JPG 19-Mar-2026 23:26 2.3M")
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.month == 3
    assert parsed.tzinfo is not None
