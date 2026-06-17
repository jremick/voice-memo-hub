from __future__ import annotations

from pathlib import Path

from voice_memo_hub.actions import extract_action_candidates, list_action_candidates, update_action_status
from voice_memo_hub.automation import run_policy_automation
from voice_memo_hub.store import connect, init_db


def seed_action(db: Path, text: str = "Ask Codex to prepare this task.") -> int:
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO recordings (
              id, source_unique_id, source_path, recorded_at, duration_seconds
            )
            VALUES ('rec1', 'rec1', 'rec1.m4a', '2026-06-17T00:00:00+00:00', 12.0)
            """
        )
        conn.execute(
            """
            INSERT INTO transcript_versions (recording_id, model_name, text)
            VALUES ('rec1', 'test-model', ?)
            """,
            (text,),
        )
        conn.commit()
    assert extract_action_candidates(db) == 1
    return int(list_action_candidates(db)[0]["id"])


def test_auto_policy_prepares_codex_task_once(tmp_path: Path) -> None:
    db = tmp_path / "hub.sqlite"
    runtime = tmp_path / "runtime"
    init_db(db)
    action_id = seed_action(db)
    policy = {
        "version": 1,
        "rules": [
            {
                "id": "prepare-codex-safe",
                "enabled": True,
                "mode": "auto",
                "reason": "local outbox only",
                "match": {"kind": "codex_request_candidate", "statuses": ["candidate"]},
                "action": {"type": "prepare_codex_task"},
            }
        ],
    }

    results = run_policy_automation(db, runtime, policy)
    second_results = run_policy_automation(db, runtime, policy)

    assert results[0].status == "done"
    assert results[0].output_path
    assert Path(results[0].output_path).exists()
    assert f"Action ID: {action_id}" in Path(results[0].output_path).read_text(encoding="utf-8")
    assert second_results[0].status == "skipped"


def test_approval_required_policy_waits_for_approval(tmp_path: Path) -> None:
    db = tmp_path / "hub.sqlite"
    runtime = tmp_path / "runtime"
    init_db(db)
    action_id = seed_action(db)
    policy = {
        "version": 1,
        "rules": [
            {
                "id": "approved-prep",
                "enabled": True,
                "mode": "approval_required",
                "reason": "prepare after approval",
                "match": {"kind": "codex_request_candidate", "statuses": ["approved"]},
                "action": {"type": "prepare_codex_task"},
            }
        ],
    }

    assert run_policy_automation(db, runtime, policy) == []

    update_action_status(db, action_id, "approved", "test approval")
    results = run_policy_automation(db, runtime, policy)

    assert results[0].status == "done"
    assert results[0].output_path


def test_auto_reference_policy_marks_reviewed(tmp_path: Path) -> None:
    db = tmp_path / "hub.sqlite"
    runtime = tmp_path / "runtime"
    init_db(db)
    seed_action(db, "This is a quiet reference about an idea.")
    policy = {
        "version": 1,
        "rules": [
            {
                "id": "reference-reviewed",
                "enabled": True,
                "mode": "auto",
                "reason": "reference-only DB update",
                "match": {"kind": "reference", "statuses": ["candidate"]},
                "action": {"type": "mark_reviewed"},
            }
        ],
    }

    results = run_policy_automation(db, runtime, policy)

    assert results[0].status == "done"
    assert list_action_candidates(db, "reviewed")[0]["kind"] == "reference"
