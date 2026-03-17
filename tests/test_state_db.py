from pathlib import Path

from gopro_gardening.state_db import StateDB


def test_state_db_roundtrip(tmp_path: Path) -> None:
    db = StateDB(tmp_path / "state.sqlite3")
    assert not db.has_downloaded("100GOPRO", "G001.jpg")
    db.record_download("100GOPRO", "G001.jpg", "/tmp/G001.jpg", 100, "2026-03-17T00:00:00", "2026-03-17")
    assert db.has_downloaded("100GOPRO", "G001.jpg")
