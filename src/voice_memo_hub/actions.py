from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional, Tuple

from .store import connect


TASK_PATTERNS = [
    r"\bneed to\b",
    r"\bremember to\b",
    r"\bremind me\b",
    r"\bfollow up\b",
    r"\bto do\b",
    r"\btask\b",
]

CODEX_PATTERNS = [
    r"\bcodex\b",
    r"\bautomate\b",
    r"\bbackground\b",
    r"\brun\b",
    r"\bbuild\b",
    r"\bfix\b",
    r"\bnotify\b",
    r"\bnotification\b",
    r"\balert\b",
]


def classify_text(text: str) -> Tuple[str, float]:
    lower = text.lower()
    if any(re.search(pattern, lower) for pattern in CODEX_PATTERNS):
        return "codex_request_candidate", 0.45
    if any(re.search(pattern, lower) for pattern in TASK_PATTERNS):
        return "task_candidate", 0.5
    return "reference", 0.35


def extract_action_candidates(db_path: Path, recording_id: Optional[str] = None) -> int:
    where = "WHERE r.id = ?" if recording_id else ""
    params = (recording_id,) if recording_id else ()
    inserted = 0

    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT r.id AS recording_id, tv.text
            FROM recordings r
            JOIN transcript_versions tv ON tv.recording_id = r.id
            WHERE tv.id = (
              SELECT MAX(id) FROM transcript_versions latest
              WHERE latest.recording_id = r.id
            )
            {'AND r.id = ?' if recording_id else ''}
            """,
            params,
        ).fetchall()

        for row in rows:
            text = (row["text"] or "").strip()
            if not text:
                continue
            kind, confidence = classify_text(text)
            exists = conn.execute(
                """
                SELECT 1 FROM action_candidates
                WHERE recording_id = ? AND kind = ? AND details = ?
                """,
                (row["recording_id"], kind, text),
            ).fetchone()
            if exists:
                continue
            title = text[:80].strip()
            conn.execute(
                """
                INSERT INTO action_candidates (
                  recording_id, kind, title, details, confidence, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["recording_id"],
                    kind,
                    title,
                    text,
                    confidence,
                    json.dumps({"extractor": "heuristic-v0"}),
                ),
            )
            inserted += 1
        conn.commit()

    return inserted


def list_action_candidates(
    db_path: Path,
    status: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    where = "WHERE ac.status = ?" if status else ""
    params: list[object] = [status] if status else []
    params.append(limit)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT ac.*, r.recorded_at, r.duration_seconds, r.transcript_status
            FROM action_candidates ac
            JOIN recordings r ON r.id = ac.recording_id
            {where}
            ORDER BY ac.created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_action_candidate(db_path: Path, action_id: int) -> Optional[dict]:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT ac.*, r.recorded_at, r.duration_seconds, r.source_path,
                   r.transcript_status
            FROM action_candidates ac
            JOIN recordings r ON r.id = ac.recording_id
            WHERE ac.id = ?
            """,
            (action_id,),
        ).fetchone()
    return dict(row) if row else None


def update_action_status(
    db_path: Path,
    action_id: int,
    status: str,
    note: Optional[str] = None,
) -> dict:
    if status not in {"candidate", "approved", "rejected", "dispatched", "done", "reviewed"}:
        raise ValueError(f"Unsupported action status: {status}")
    with connect(db_path) as conn:
        row = conn.execute("SELECT metadata_json FROM action_candidates WHERE id = ?", (action_id,)).fetchone()
        if not row:
            raise LookupError(f"Action candidate not found: {action_id}")
        metadata = json.loads(row["metadata_json"] or "{}")
        if note:
            metadata.setdefault("notes", []).append(note)
        conn.execute(
            """
            UPDATE action_candidates
            SET status = ?, metadata_json = ?
            WHERE id = ?
            """,
            (status, json.dumps(metadata, sort_keys=True), action_id),
        )
        conn.commit()
    action = get_action_candidate(db_path, action_id)
    assert action is not None
    return action


def prepare_codex_task(db_path: Path, action_id: int) -> str:
    action = get_action_candidate(db_path, action_id)
    if not action:
        raise LookupError(f"Action candidate not found: {action_id}")

    risk = "medium" if action["kind"] == "codex_request_candidate" else "low"
    if action["kind"] == "reference":
        risk = "review-only"

    return f"""# Voice Memo Hub Candidate

Action ID: {action['id']}
Recording ID: {action['recording_id']}
Recorded At: {action['recorded_at']}
Kind: {action['kind']}
Status: {action['status']}
Risk: {risk}

## Transcript-Derived Request

{action['details']}

## Instructions For Codex

1. Treat this as a candidate inferred from a voice memo, not a direct command.
2. Restate the intended task and assumptions before making changes.
3. Do not write to external systems, commit, push, send messages, or delete files unless the action has explicit approval.
4. Prefer a small read-only investigation first when the task is ambiguous.
5. Report what changed, what was verified, and any open loops back to Voice Memo Hub.
"""


def record_dispatch(db_path: Path, action_id: int, runner: str, result: dict) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO workflow_runs (action_candidate_id, runner, status, result_json)
            VALUES (?, ?, ?, ?)
            """,
            (action_id, runner, result.get("status", "queued"), json.dumps(result, sort_keys=True)),
        )
        conn.execute("UPDATE action_candidates SET status = 'dispatched' WHERE id = ?", (action_id,))
        conn.commit()
        return int(cursor.lastrowid)
