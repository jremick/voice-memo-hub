# Voice Memo Hub Instructions

Version: 0.1.0a2
Last updated: 2026-06-17

## Scope

This repo builds Voice Memo Hub: an always-on Mac ingestion,
transcription, indexing, and workflow handoff system for Apple Voice Memos.

## Boundaries

- Keep source code, tests, docs, and templates in git.
- Keep runtime audio, transcripts, SQLite databases, logs, and local queue state
  outside git.
- Default runtime data path:
  `~/Library/Application Support/voice-memo-hub`.
- Do not commit secrets, API keys, raw audio, generated transcripts, or
  machine-local launchd installs.

## Operating Rules

- The configured service machine is the canonical always-on processor.
- Other Macs and apps should query via CLI/API/snapshots, not by writing the
  canonical database directly.
- New workflows that mutate external systems must be queued for review unless an
  explicit allowlist and approval rule exists.
- Prefer local transcription first. Cloud transcription is opt-in per workflow.

## Verification

Before claiming a change is ready, run:

```bash
python3 -m pytest
python3 -m voice_memo_hub.cli --help
```
