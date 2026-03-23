from __future__ import annotations

from pathlib import Path

from gopro_gardening.sdcard_sync import SDCardSyncEngine
from gopro_gardening.state_db import StateDB


def _make_engine(tmp_path: Path, source_root: Path) -> tuple[SDCardSyncEngine, StateDB, Path, Path]:
    raw_dir = tmp_path / "raw"
    indexed_dir = tmp_path / "indexed"
    state_db = StateDB(tmp_path / "state.sqlite3")
    engine = SDCardSyncEngine(
        state_db=state_db,
        source_dir=source_root,
        raw_dir=raw_dir,
        indexed_dir=indexed_dir,
        media_extensions=[".jpg", ".jpeg", ".gpr"],
        timezone_name="UTC",
    )
    return engine, state_db, raw_dir, indexed_dir


def test_sdcard_sync_imports_and_records_files(tmp_path: Path) -> None:
    sdmount = tmp_path / "sdmount"
    (sdmount / "DCIM" / "100GOPRO").mkdir(parents=True)
    (sdmount / "DCIM" / "101GOPRO").mkdir(parents=True)
    (sdmount / "DCIM" / "100GOPRO" / "A001.JPG").write_bytes(b"a001")
    (sdmount / "DCIM" / "101GOPRO" / "B001.JPG").write_bytes(b"b001")
    (sdmount / "DCIM" / "101GOPRO" / "CLIP01.MP4").write_bytes(b"video")

    engine, state_db, raw_dir, indexed_dir = _make_engine(tmp_path, sdmount)
    stats = engine.sync_missing_files()

    assert stats["remote_total"] == 3
    assert stats["eligible_total"] == 2
    assert stats["downloaded"] == 2
    assert stats["ignored_extension"] == 1
    assert stats["failed"] == 0
    assert state_db.has_downloaded("100GOPRO", "A001.JPG")
    assert state_db.has_downloaded("101GOPRO", "B001.JPG")
    assert (raw_dir / "100GOPRO" / "A001.JPG").exists()
    assert (raw_dir / "101GOPRO" / "B001.JPG").exists()
    assert any(indexed_dir.rglob("*.JPG"))

    stats_second = engine.sync_missing_files()
    assert stats_second["downloaded"] == 0
    assert stats_second["skipped"] == 2


def test_sdcard_sync_registers_existing_raw_file_without_copy(tmp_path: Path) -> None:
    sdmount = tmp_path / "sdmount"
    (sdmount / "DCIM" / "100GOPRO").mkdir(parents=True)
    source_file = sdmount / "DCIM" / "100GOPRO" / "A001.JPG"
    source_file.write_bytes(b"a001")

    engine, state_db, raw_dir, _indexed_dir = _make_engine(tmp_path, sdmount)
    raw_target = raw_dir / "100GOPRO" / "A001.JPG"
    raw_target.parent.mkdir(parents=True, exist_ok=True)
    raw_target.write_bytes(b"xxxx")

    stats = engine.sync_missing_files()

    assert stats["downloaded"] == 0
    assert stats["registered_existing"] == 1
    assert stats["failed"] == 0
    assert state_db.has_downloaded("100GOPRO", "A001.JPG")


def test_sdcard_sync_overwrites_mismatched_existing_raw_file(tmp_path: Path) -> None:
    sdmount = tmp_path / "sdmount"
    (sdmount / "DCIM" / "100GOPRO").mkdir(parents=True)
    source_file = sdmount / "DCIM" / "100GOPRO" / "A001.JPG"
    source_file.write_bytes(b"source-bytes")

    engine, state_db, raw_dir, _indexed_dir = _make_engine(tmp_path, sdmount)
    raw_target = raw_dir / "100GOPRO" / "A001.JPG"
    raw_target.parent.mkdir(parents=True, exist_ok=True)
    raw_target.write_bytes(b"tiny")

    stats = engine.sync_missing_files()

    assert stats["downloaded"] == 1
    assert stats["registered_existing"] == 0
    assert stats["failed"] == 0
    assert raw_target.read_bytes() == b"source-bytes"
    assert state_db.has_downloaded("100GOPRO", "A001.JPG")
