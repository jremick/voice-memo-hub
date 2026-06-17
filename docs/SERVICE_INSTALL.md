# Always-On Mac Install

Version: 0.1.0a2
Last updated: 2026-06-17

Voice Memo Hub can run on an always-on Mac that has iCloud Voice Memos sync
enabled for the account running the service.

## Paths

Choose a project path and runtime path for the service account:

```text
<project-path>/voice-memo-hub
~/Library/Application Support/voice-memo-hub
```

Runtime data contains audio, transcripts, logs, policy files, and local workflow
state. Keep it outside git.

## Bootstrap

```bash
cd <project-path>/voice-memo-hub
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools
.venv/bin/python -m pip install . pytest
.venv/bin/python -m pytest
.venv/bin/memo doctor
.venv/bin/memo policy
.venv/bin/memo automate --dry-run
```

For transcription support:

```bash
.venv/bin/python -m pip install ".[transcribe]"
```

## Codex MCP

Add the MCP server using the Python executable from your project venv:

```toml
[mcp_servers.voice_memo_hub]
command = "<project-path>/voice-memo-hub/.venv/bin/python"
args = ["-m", "voice_memo_hub.mcp_server"]
startup_timeout_sec = 30.0
```

Sanity checks:

```bash
cd <project-path>/voice-memo-hub
.venv/bin/python -m pytest
.venv/bin/memo doctor
.venv/bin/memo inbox --limit 5
```

## launchd

Install only after `memo doctor` reports that the Voice Memos source directory
and `CloudRecordings.db` exist.

On some Macs, direct launchd access to the Voice Memos app group may be blocked
by macOS privacy controls. If so, run the command through a user-approved path
or adapt the template to your local access model.

Copy the template, replace placeholder paths, then bootstrap it:

```bash
mkdir -p "$HOME/Library/LaunchAgents"
cp launchd/com.example.voice-memo-hub.plist.template \
  "$HOME/Library/LaunchAgents/com.example.voice-memo-hub.plist"
```

Edit these placeholder values in the copied plist:

```text
__VOICE_MEMO_HUB_BIN__
__VOICE_MEMO_HUB_LOG_DIR__
```

Then load the LaunchAgent:

```bash
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.example.voice-memo-hub.plist"
launchctl enable "gui/$(id -u)/com.example.voice-memo-hub"
```

## Voice Memos Sync

The service account must have iCloud Voice Memos sync enabled. Verify the local
synced source exists before enabling launchd:

```bash
.venv/bin/memo doctor
```
