# Changelog

## 0.1.0-alpha.2 - 2026-06-17

Public-surface cleanup release candidate.

- Removed maintainer-specific names and local machine paths from tracked files.
- Replaced host-specific launchd and install docs with placeholder-based service docs.
- Removed built-in provider-specific notification integration and policy examples.
- Kept automation actions limited to local review updates, local outbox files, and fixed-template macOS notifications.

## 0.1.0-alpha.1 - 2026-06-17

Initial public-alpha release candidate.

- Added Apple Voice Memos ingestion into a local runtime archive.
- Added SQLite metadata, transcript storage, and FTS5 transcript search.
- Added optional local MLX Whisper transcription.
- Added heuristic action candidate extraction and review lifecycle commands.
- Added Codex task prompt preparation and dispatch recording.
- Added stdio MCP server for read-first Codex access.
- Added external policy loading and a narrow safe automation dispatcher.
- Added always-on Mac launchd template and installation notes.
