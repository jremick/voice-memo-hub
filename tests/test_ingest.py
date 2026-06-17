from __future__ import annotations

import sqlite3
from pathlib import Path

from voice_memo_hub.ingest import AssetCandidate, SourceRecording, ingest, match_assets_by_duration
from voice_memo_hub.paths import ensure_runtime_dirs
from voice_memo_hub.store import connect, init_db


def create_voice_memos_source(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "sample.m4a").write_bytes(b"fake audio")
    conn = sqlite3.connect(path / "CloudRecordings.db")
    conn.execute(
        """
        CREATE TABLE ZCLOUDRECORDING (
          ZUNIQUEID VARCHAR,
          ZPATH VARCHAR,
          ZCUSTOMLABEL VARCHAR,
          ZDATE TIMESTAMP,
          ZDURATION FLOAT,
          ZLOCALDURATION FLOAT,
          ZFLAGS INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO ZCLOUDRECORDING
        VALUES ('abc-123', 'sample.m4a', 'Test memo', 803341568, 12.5, 12.5, 772)
        """
    )
    conn.commit()
    conn.close()


def test_ingest_archives_recording(tmp_path: Path) -> None:
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    db = runtime / "db" / "voice_memo_hub.sqlite"
    create_voice_memos_source(source)
    ensure_runtime_dirs(runtime)
    init_db(db)

    result = ingest(source, runtime, db)

    assert result == {"seen": 1, "inserted": 1, "updated": 0, "missing": 0}
    with connect(db) as conn:
        row = conn.execute("SELECT * FROM recordings WHERE source_unique_id = 'abc-123'").fetchone()
    assert row is not None
    assert row["title"] == "Test memo"
    assert Path(row["archive_path"]).exists()


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    db = runtime / "db" / "voice_memo_hub.sqlite"
    create_voice_memos_source(source)
    ensure_runtime_dirs(runtime)
    init_db(db)

    ingest(source, runtime, db)
    result = ingest(source, runtime, db)

    assert result["inserted"] == 0
    assert result["updated"] == 1


def test_duration_asset_matching_handles_null_zpath(tmp_path: Path) -> None:
    recordings = [
        SourceRecording("rec-a", None, None, None, 58.339, 0.0, 2),
        SourceRecording("rec-b", None, None, None, 4.478, 0.0, 2),
    ]
    assets = [
        AssetCandidate(tmp_path / "asset-a", 58.364),
        AssetCandidate(tmp_path / "asset-b", 4.54),
    ]

    matches = match_assets_by_duration(recordings, assets)

    assert matches["rec-a"].path.name == "asset-a"
    assert matches["rec-b"].path.name == "asset-b"
