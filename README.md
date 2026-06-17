# Voice Memo Hub

![Python](https://img.shields.io/badge/python-%3E%3D3.9-brightgreen.svg)
![Status](https://img.shields.io/badge/status-alpha-yellow.svg)
[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)

Voice Memo Hub turns Apple Voice Memos into a local inbox for transcription,
search, review, and safe Codex workflow handoff.

It is designed for an always-on Mac that ingests synced Voice Memos, transcribes
them locally when configured, indexes them in SQLite, and prepares bounded
workflow candidates for humans or agents to review.

> Alpha: this project is early. CLI flags, policy shape, data schema, and install
> flow may change before beta.

## What It Does

- Reads Apple Voice Memos metadata from the local synced Voice Memos container.
- Copies new `.m4a` files into a managed private archive outside the repo.
- Stores durable metadata in SQLite.
- Indexes transcripts with SQLite FTS5.
- Optionally transcribes locally with MLX Whisper.
- Extracts conservative action candidates for review.
- Applies narrow external automation policy for safe local handling.
- Exposes a small stdio MCP server for Codex and other clients.

## Privacy Model

The repo contains code, docs, and generic examples only. Runtime data belongs
outside git:

```text
~/Library/Application Support/voice-memo-hub/
```

That runtime directory may contain raw audio, transcripts, logs, policy files,
workflow state, and local outbox files. Do not commit it.

Automation policy is runtime configuration, not app code. See
[docs/POLICY.md](docs/POLICY.md).

## Current Status

This repo is in public alpha. The core local workflow is available:

- ingest synced Apple Voice Memos
- transcribe selected recordings with optional local dependencies
- search transcripts
- extract and review action candidates
- prepare Codex task prompts
- run a narrow safe automation dispatcher
- serve read-first MCP tools

Known limitations:

- macOS Voice Memos storage is private app data and can be affected by Apple
  sync and privacy behavior.
- launchd may need a host-specific access workaround on some Macs.
- automatic action execution is intentionally limited to local status updates,
  local outbox files, and fixed-template notifications.
- no hosted API or packaged installer is provided yet.
- schema migrations are not stabilized for long-lived external users.

## Quick Start

Prerequisites: macOS, Python 3.9+, local access to the synced Voice Memos
container, and optional MLX Whisper dependencies for transcription.

```bash
git clone https://github.com/OWNER/voice-memo-hub.git
cd voice-memo-hub
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[transcribe]"
memo doctor
memo ingest
memo list
memo search "idea"
memo transcribe --pending --limit 2 --max-duration-seconds 1800
memo actions --extract
memo inbox
memo automate --dry-run
```

Without the optional `transcribe` dependencies, ingest/search still works after
transcripts are available.

## Common Commands

```bash
memo doctor
memo run-once --transcribe --limit 2 --max-duration-seconds 1800 --apply-policy
memo digest --limit 10
memo policy
memo policy --check <action_id>
memo automate --dry-run
memo approve <action_id> --note "reason"
memo prepare-codex-task <action_id>
memo dispatch <action_id> --runner codex
```

`dispatch` records a handoff in `workflow_runs`; it does not execute arbitrary
work by itself. Codex should use `prepare-codex-task` as the safe prompt source.

## Default Paths

Voice Memos source:

```text
~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings
```

Voice Memo Hub runtime:

```text
~/Library/Application Support/voice-memo-hub
```

External policy:

```text
~/Library/Application Support/voice-memo-hub/config/policy.json
```

## Automation Safety

The dispatcher only runs allowlisted action types:

- `mark_reviewed`: local database status update.
- `prepare_codex_task`: writes a prompt file under runtime `outbox/`.
- `local_notification`: fixed-template macOS notification.

External writes, deploys, commits, pushes, public posts, email, work-system
updates, and device-control actions should remain `manual` or
`approval_required` policy rules.

See [config/automation-policy.example.json](config/automation-policy.example.json)
for a generic starter policy.

## Codex MCP

Voice Memo Hub includes a stdio MCP server for Codex:

```toml
[mcp_servers.voice_memo_hub]
command = "/path/to/voice-memo-hub/.venv/bin/python"
args = ["-m", "voice_memo_hub.mcp_server"]
startup_timeout_sec = 30.0
```

The MCP server exposes read-first tools for recent memos, transcript search,
recording detail, action candidates, marking reviewed, prompt preparation, and
digest rendering.

## Documentation

- [Always-on Mac install](docs/SERVICE_INSTALL.md)
- [External automation policy](docs/POLICY.md)
- [Project plan](docs/PROJECT_PLAN.md)
- [Roadmap](ROADMAP.md)
- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[transcribe]"
python3 -m pytest
python3 -m voice_memo_hub.cli --help
```

## Community And Support

- Use GitHub Issues for bugs and concrete feature requests.
- Security reports should follow [SECURITY.md](SECURITY.md).
- External contributions are welcome after alpha expectations are documented in
  [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE) - Copyright 2026 Voice Memo Hub contributors.
