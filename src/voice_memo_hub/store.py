from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS recordings (
  id TEXT PRIMARY KEY,
  source_unique_id TEXT UNIQUE,
  source_path TEXT NOT NULL,
  source_db_path TEXT,
  title TEXT,
  recorded_at TEXT,
  duration_seconds REAL,
  local_duration_seconds REAL,
  file_size_bytes INTEGER,
  audio_sha256 TEXT,
  archive_path TEXT,
  codec TEXT,
  sample_rate INTEGER,
  channels INTEGER,
  ingest_status TEXT NOT NULL DEFAULT 'new',
  transcript_status TEXT NOT NULL DEFAULT 'pending',
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS transcript_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  model_name TEXT NOT NULL,
  model_version TEXT,
  language TEXT,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  processing_seconds REAL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS transcript_segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  transcript_version_id INTEGER NOT NULL REFERENCES transcript_versions(id) ON DELETE CASCADE,
  start_seconds REAL,
  end_seconds REAL,
  text TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS action_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  details TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',
  confidence REAL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS workflow_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action_candidate_id INTEGER REFERENCES action_candidates(id) ON DELETE SET NULL,
  runner TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  result_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS recordings_recorded_at_idx ON recordings(recorded_at);
CREATE INDEX IF NOT EXISTS recordings_transcript_status_idx ON recordings(transcript_status);
CREATE INDEX IF NOT EXISTS transcript_versions_recording_id_idx ON transcript_versions(recording_id);
CREATE INDEX IF NOT EXISTS transcript_segments_transcript_version_id_idx ON transcript_segments(transcript_version_id);
CREATE INDEX IF NOT EXISTS action_candidates_status_kind_idx ON action_candidates(status, kind);

CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
  recording_id UNINDEXED,
  text
);

CREATE TRIGGER IF NOT EXISTS transcript_versions_after_insert
AFTER INSERT ON transcript_versions
BEGIN
  INSERT INTO transcript_fts(rowid, recording_id, text)
  VALUES (new.id, new.recording_id, new.text);
END;
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: Path) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)
