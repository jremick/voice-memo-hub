from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

from .store import connect


APPLE_EPOCH_OFFSET = 978_307_200


@dataclass(frozen=True)
class SourceRecording:
    unique_id: str
    path: Optional[str]
    title: Optional[str]
    recorded_at: Optional[str]
    duration_seconds: Optional[float]
    local_duration_seconds: Optional[float]
    flags: Optional[int]


@dataclass(frozen=True)
class AssetCandidate:
    path: Path
    duration_seconds: float


def apple_timestamp_to_iso(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value + APPLE_EPOCH_OFFSET, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_source_recordings(source_dir: Path) -> list[SourceRecording]:
    db_path = source_dir / "CloudRecordings.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Voice Memos database not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT ZUNIQUEID, ZPATH, ZCUSTOMLABEL, ZDATE, ZDURATION,
                   ZLOCALDURATION, ZFLAGS
            FROM ZCLOUDRECORDING
            ORDER BY ZDATE
            """
        ).fetchall()
    finally:
        conn.close()

    recordings: list[SourceRecording] = []
    for row in rows:
        recordings.append(
            SourceRecording(
                unique_id=row["ZUNIQUEID"] or str(uuid.uuid4()),
                path=row["ZPATH"],
                title=row["ZCUSTOMLABEL"],
                recorded_at=apple_timestamp_to_iso(row["ZDATE"]),
                duration_seconds=row["ZDURATION"],
                local_duration_seconds=row["ZLOCALDURATION"],
                flags=row["ZFLAGS"],
            )
        )
    return recordings


def archive_name(recording: SourceRecording, source_file: Path) -> str:
    suffix = source_file.suffix or ".m4a"
    return f"{recording.unique_id}{suffix}"


def audio_duration(path: Path) -> Optional[float]:
    try:
        result = subprocess.run(
            ["afinfo", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    for line in result.stdout.splitlines():
        marker = "estimated duration:"
        if marker in line:
            value = line.split(marker, 1)[1].strip().split(" ", 1)[0]
            try:
                return float(value)
            except ValueError:
                return None
    return None


def asset_search_dirs(source_dir: Path) -> Iterable[Path]:
    yield source_dir / "CloudRecordings_ckAssets"
    yield source_dir / ".CloudRecordings_SUPPORT" / "_FBF"


def downloaded_assets(source_dir: Path) -> list[AssetCandidate]:
    candidates: list[AssetCandidate] = []
    for directory in asset_search_dirs(source_dir):
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if not path.is_file():
                continue
            duration = audio_duration(path)
            if duration is not None:
                candidates.append(AssetCandidate(path=path, duration_seconds=duration))
    return candidates


def match_assets_by_duration(
    recordings: list[SourceRecording],
    assets: list[AssetCandidate],
    tolerance_seconds: float = 0.75,
) -> Dict[str, AssetCandidate]:
    unmatched = list(assets)
    matches: Dict[str, AssetCandidate] = {}
    for recording in sorted(recordings, key=lambda item: item.duration_seconds or 0):
        if recording.path or recording.duration_seconds is None:
            continue
        best: Optional[AssetCandidate] = None
        best_delta = tolerance_seconds
        for asset in unmatched:
            delta = abs(asset.duration_seconds - recording.duration_seconds)
            if delta <= best_delta:
                best = asset
                best_delta = delta
        if best is not None:
            matches[recording.unique_id] = best
            unmatched.remove(best)
    return matches


def ingest(source_dir: Path, runtime_dir: Path, db_path: Path) -> dict[str, int]:
    source_rows = read_source_recordings(source_dir)
    asset_matches = match_assets_by_duration(source_rows, downloaded_assets(source_dir))
    archive_dir = runtime_dir / "audio" / "originals"
    archive_dir.mkdir(parents=True, exist_ok=True)

    inserted = 0
    updated = 0
    missing = 0

    with connect(db_path) as conn:
        for source in source_rows:
            match_method = "zpath"
            if source.path:
                source_file = source_dir / source.path
                display_source_path = source.path
            elif source.unique_id in asset_matches:
                match_method = "duration_asset"
                source_file = asset_matches[source.unique_id].path
                display_source_path = str(source_file.relative_to(source_dir))
            else:
                missing += 1
                continue

            if not source_file.exists():
                missing += 1
                continue

            archive_path = archive_dir / archive_name(source, source_file)
            if not archive_path.exists():
                shutil.copy2(source_file, archive_path)

            file_hash = sha256_file(archive_path)
            stat = archive_path.stat()
            recording_id = source.unique_id
            metadata = {"voice_memos_flags": source.flags, "source_match_method": match_method}
            existing = conn.execute(
                "SELECT id FROM recordings WHERE source_unique_id = ?",
                (source.unique_id,),
            ).fetchone()

            conn.execute(
                """
                INSERT INTO recordings (
                  id, source_unique_id, source_path, source_db_path, title,
                  recorded_at, duration_seconds, local_duration_seconds,
                  file_size_bytes, audio_sha256, archive_path, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_unique_id) DO UPDATE SET
                  source_path = excluded.source_path,
                  source_db_path = excluded.source_db_path,
                  title = excluded.title,
                  recorded_at = excluded.recorded_at,
                  duration_seconds = excluded.duration_seconds,
                  local_duration_seconds = excluded.local_duration_seconds,
                  file_size_bytes = excluded.file_size_bytes,
                  audio_sha256 = excluded.audio_sha256,
                  archive_path = excluded.archive_path,
                  ingest_status = 'archived',
                  last_seen_at = CURRENT_TIMESTAMP,
                  metadata_json = excluded.metadata_json
                """,
                (
                    recording_id,
                    source.unique_id,
                    display_source_path,
                    str(source_dir / "CloudRecordings.db"),
                    source.title,
                    source.recorded_at,
                    source.duration_seconds,
                    source.local_duration_seconds,
                    stat.st_size,
                    file_hash,
                    str(archive_path),
                    json.dumps(metadata, sort_keys=True),
                ),
            )
            if existing:
                updated += 1
            else:
                inserted += 1

        conn.commit()

    return {"seen": len(source_rows), "inserted": inserted, "updated": updated, "missing": missing}
