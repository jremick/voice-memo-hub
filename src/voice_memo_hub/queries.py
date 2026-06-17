from __future__ import annotations

from pathlib import Path
from typing import Optional

from .store import connect


def recent_recordings(db_path: Path, limit: int = 10) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT r.*, tv.text AS transcript_text, tv.created_at AS transcript_created_at
            FROM recordings r
            LEFT JOIN transcript_versions tv ON tv.id = (
              SELECT MAX(id) FROM transcript_versions latest
              WHERE latest.recording_id = r.id
            )
            ORDER BY r.recorded_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def search_transcripts(db_path: Path, query: str, limit: int = 20) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.recorded_at, r.duration_seconds,
                   snippet(transcript_fts, 1, '[', ']', '...', 18) AS snippet
            FROM transcript_fts
            JOIN recordings r ON r.id = transcript_fts.recording_id
            WHERE transcript_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def recording_detail(db_path: Path, recording_id: str) -> Optional[dict]:
    with connect(db_path) as conn:
        recording = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
        if not recording:
            return None
        transcript = conn.execute(
            """
            SELECT * FROM transcript_versions
            WHERE recording_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (recording_id,),
        ).fetchone()
        segments = conn.execute(
            """
            SELECT ts.*
            FROM transcript_segments ts
            JOIN transcript_versions tv ON tv.id = ts.transcript_version_id
            WHERE tv.recording_id = ?
              AND tv.id = (
                SELECT MAX(id) FROM transcript_versions latest
                WHERE latest.recording_id = tv.recording_id
              )
            ORDER BY ts.start_seconds
            """,
            (recording_id,),
        ).fetchall()
    return {
        "recording": dict(recording),
        "transcript": dict(transcript) if transcript else None,
        "segments": [dict(row) for row in segments],
    }


def digest(db_path: Path, limit: int = 10) -> str:
    rows = recent_recordings(db_path, limit)
    lines = ["# Voice Memo Hub Digest", ""]
    for row in rows:
        text = (row.get("transcript_text") or "").strip()
        excerpt = text[:260] + ("..." if len(text) > 260 else "")
        lines.extend(
            [
                f"## {row['recorded_at']} ({row['transcript_status']})",
                "",
                f"- Recording: `{row['id']}`",
                f"- Duration: {row['duration_seconds']:.1f}s" if row["duration_seconds"] is not None else "- Duration: unknown",
                f"- Source: `{row['source_path']}`",
                "",
                excerpt or "_No transcript text._",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
