from __future__ import annotations

import json
import subprocess
import time
import warnings
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from .store import connect


DEFAULT_MODEL = "mlx-community/whisper-small.en-mlx-q4"


def convert_to_wav(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(source), str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )


def load_wav_array(wav_path: Path) -> Any:
    try:
        import numpy as np
        from scipy.io import wavfile
    except ImportError as exc:
        raise RuntimeError("Install the transcribe extra: pip install -e '.[transcribe]'") from exc

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rate, data = wavfile.read(str(wav_path))
    if rate != 16_000:
        raise RuntimeError(f"Expected 16000 Hz WAV, got {rate} Hz: {wav_path}")
    if getattr(data, "ndim", 1) > 1:
        data = data[:, 0]
    if np.issubdtype(data.dtype, np.integer):
        data = data.astype(np.float32) / np.iinfo(data.dtype).max
    else:
        data = data.astype(np.float32)
    peak = float(np.max(np.abs(data))) or 1.0
    return np.clip(data / peak * 0.8, -1, 1).astype(np.float32)


def transcribe_audio(audio_path: Path, derived_dir: Path, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    try:
        import mlx_whisper
    except ImportError as exc:
        raise RuntimeError("Install the transcribe extra: pip install -e '.[transcribe]'") from exc

    wav_path = derived_dir / f"{audio_path.stem}.wav"
    if not wav_path.exists():
        convert_to_wav(audio_path, wav_path)

    start = time.monotonic()
    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        result = mlx_whisper.transcribe(
            load_wav_array(wav_path),
            path_or_hf_repo=model,
            language="en",
            verbose=False,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,
        )
    result["_processing_seconds"] = time.monotonic() - start
    return result


def store_transcript(db_path: Path, recording_id: str, result: dict[str, Any], model: str) -> int:
    text = (result.get("text") or "").strip()
    segments = result.get("segments") or []
    metadata = {k: v for k, v in result.items() if k not in {"text", "segments"}}

    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO transcript_versions (
              recording_id, model_name, language, text, processing_seconds, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                recording_id,
                model,
                result.get("language"),
                text,
                result.get("_processing_seconds"),
                json.dumps(metadata, sort_keys=True, default=str),
            ),
        )
        transcript_id = int(cursor.lastrowid)
        for segment in segments:
            conn.execute(
                """
                INSERT INTO transcript_segments (
                  transcript_version_id, start_seconds, end_seconds, text, metadata_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    transcript_id,
                    segment.get("start"),
                    segment.get("end"),
                    (segment.get("text") or "").strip(),
                    json.dumps(segment, sort_keys=True, default=str),
                ),
            )
        status = "complete" if text else "empty"
        conn.execute(
            "UPDATE recordings SET transcript_status = ? WHERE id = ?",
            (status, recording_id),
        )
        conn.commit()
        return transcript_id
