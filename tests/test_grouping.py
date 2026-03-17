from pathlib import Path

from gopro_gardening.organizer import organize_by_capture_date


def test_organize_by_capture_date(tmp_path: Path) -> None:
    src = tmp_path / "src.jpg"
    src.write_bytes(b"123")
    indexed = tmp_path / "indexed"
    dst = organize_by_capture_date(src, indexed, "2026-03-17")
    assert dst.exists()
    assert dst.parent.name == "2026-03-17"
