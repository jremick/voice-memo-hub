from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "voice-memo-hub"
VOICE_MEMOS_RELATIVE = Path(
    "Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings"
)


def home() -> Path:
    return Path.home()


def default_source_dir() -> Path:
    return home() / VOICE_MEMOS_RELATIVE


def default_runtime_dir() -> Path:
    override = os.environ.get("VOICE_MEMO_HUB_HOME")
    if override:
        return Path(override).expanduser()
    return home() / "Library/Application Support" / APP_NAME


def ensure_runtime_dirs(runtime_dir: Path) -> None:
    for child in [
        runtime_dir,
        runtime_dir / "audio" / "originals",
        runtime_dir / "audio" / "derived",
        runtime_dir / "config",
        runtime_dir / "db",
        runtime_dir / "exports",
        runtime_dir / "logs",
        runtime_dir / "outbox" / "codex_tasks",
    ]:
        child.mkdir(parents=True, exist_ok=True)


def db_path(runtime_dir: Path) -> Path:
    return runtime_dir / "db" / "voice_memo_hub.sqlite"
