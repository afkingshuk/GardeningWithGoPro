from pathlib import Path

from gopro_gardening.state_db import StateDB


def test_state_db_roundtrip(tmp_path: Path) -> None:
    db = StateDB(tmp_path / "state.sqlite3")
    assert not db.has_downloaded("100GOPRO", "G001.jpg")
    db.record_download(
        "100GOPRO",
        "G001.jpg",
        "/tmp/G001.jpg",
        "/tmp/indexed/2026-03-17/G001.jpg",
        100,
        "2026-03-17T00:00:00-04:00",
        "2026-03-17",
    )
    assert db.has_downloaded("100GOPRO", "G001.jpg")


def test_state_db_orders_day_media_by_capture_ts(tmp_path: Path) -> None:
    db = StateDB(tmp_path / "state.sqlite3")
    db.record_download(
        "100GOPRO",
        "G002.jpg",
        "/tmp/G002.jpg",
        "/tmp/indexed/2026-03-17/G002.jpg",
        100,
        "2026-03-17T00:02:00-04:00",
        "2026-03-17",
    )
    db.record_download(
        "100GOPRO",
        "G001.jpg",
        "/tmp/G001.jpg",
        "/tmp/indexed/2026-03-17/G001.jpg",
        100,
        "2026-03-17T00:01:00-04:00",
        "2026-03-17",
    )

    media = db.list_day_media("2026-03-17")
    assert [item.filename for item in media] == ["G001.jpg", "G002.jpg"]
