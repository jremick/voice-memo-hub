from __future__ import annotations

from pathlib import Path

from voice_memo_hub.actions import (
    extract_action_candidates,
    list_action_candidates,
    prepare_codex_task,
    record_dispatch,
    update_action_status,
)
from voice_memo_hub.queries import digest, recording_detail, search_transcripts
from voice_memo_hub.store import connect, init_db


def seed_transcript(db: Path) -> None:
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO recordings (
              id, source_unique_id, source_path, recorded_at, duration_seconds
            )
            VALUES ('rec1', 'rec1', 'rec1.m4a', '2026-06-17T00:00:00+00:00', 42.0)
            """
        )
        conn.execute(
            """
            INSERT INTO transcript_versions (recording_id, model_name, text)
            VALUES ('rec1', 'test-model', 'Ask Codex to check the memo inbox and prepare a digest.')
            """
        )
        conn.commit()


def test_action_lifecycle_and_codex_prompt(tmp_path: Path) -> None:
    db = tmp_path / "hub.sqlite"
    init_db(db)
    seed_transcript(db)

    assert extract_action_candidates(db) == 1
    action = list_action_candidates(db)[0]
    assert action["status"] == "candidate"

    approved = update_action_status(db, action["id"], "approved", "looks useful")
    assert approved["status"] == "approved"

    prompt = prepare_codex_task(db, action["id"])
    assert "Voice Memo Hub Candidate" in prompt
    assert "Ask Codex" in prompt

    run_id = record_dispatch(db, action["id"], "codex", {"status": "queued"})
    assert run_id == 1
    assert list_action_candidates(db, "dispatched")[0]["id"] == action["id"]


def test_query_helpers(tmp_path: Path) -> None:
    db = tmp_path / "hub.sqlite"
    init_db(db)
    seed_transcript(db)

    assert search_transcripts(db, "digest")[0]["id"] == "rec1"
    assert recording_detail(db, "rec1")["transcript"]["text"].startswith("Ask Codex")
    assert "Voice Memo Hub Digest" in digest(db)
