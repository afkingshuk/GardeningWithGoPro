from pathlib import Path

from gopro_gardening.metadata import extract_capture_datetime


def test_metadata_falls_back_to_mtime(tmp_path: Path) -> None:
    p = tmp_path / "fake.jpg"
    p.write_bytes(b"not-a-real-jpeg")
    dt, source = extract_capture_datetime(p)
    assert dt is not None
    assert source == "mtime"


def test_metadata_uses_configured_timezone_for_mtime(tmp_path: Path) -> None:
    p = tmp_path / "fake.jpg"
    p.write_bytes(b"not-a-real-jpeg")
    dt, source = extract_capture_datetime(p, "America/New_York")
    assert dt is not None
    assert dt.tzinfo is not None
    assert source == "mtime"
