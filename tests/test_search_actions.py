from __future__ import annotations

from pathlib import Path

from voice_memo_hub.actions import extract_action_candidates
from voice_memo_hub.store import connect, init_db


def test_transcript_fts_and_action_candidate(tmp_path: Path) -> None:
    db = tmp_path / "hub.sqlite"
    init_db(db)
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO recordings (id, source_unique_id, source_path)
            VALUES ('rec1', 'rec1', 'rec1.m4a')
            """
        )
        conn.execute(
            """
            INSERT INTO transcript_versions (recording_id, model_name, text)
            VALUES ('rec1', 'test-model', 'Remember to ask Codex to build the memo workflow.')
            """
        )
        conn.commit()

        search = conn.execute(
            "SELECT recording_id FROM transcript_fts WHERE transcript_fts MATCH 'workflow'"
        ).fetchone()
    assert search["recording_id"] == "rec1"

    inserted = extract_action_candidates(db)
    assert inserted == 1
    with connect(db) as conn:
        action = conn.execute("SELECT kind, title FROM action_candidates").fetchone()
    assert action["kind"] == "codex_request_candidate"


def test_notification_request_is_codex_candidate(tmp_path: Path) -> None:
    db = tmp_path / "hub.sqlite"
    init_db(db)
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO recordings (id, source_unique_id, source_path)
            VALUES ('rec1', 'rec1', 'rec1.m4a')
            """
        )
        conn.execute(
            """
            INSERT INTO transcript_versions (recording_id, model_name, text)
            VALUES ('rec1', 'test-model', 'Send me a notification when this transcribes.')
            """
        )
        conn.commit()

    assert extract_action_candidates(db) == 1
    with connect(db) as conn:
        action = conn.execute("SELECT kind FROM action_candidates").fetchone()
    assert action["kind"] == "codex_request_candidate"
