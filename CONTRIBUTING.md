# Contributing

Voice Memo Hub is in public alpha. Small, focused issues and pull requests are
welcome, especially around setup reliability, docs, tests, and safe local
workflow handling.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[transcribe]"
python3 -m pytest
python3 -m voice_memo_hub.cli --help
```

## Boundaries

- Do not commit raw audio, transcripts, runtime databases, logs, or local policy
  files.
- Keep site-specific automation rules outside app code.
- Keep automatic action types narrow, deterministic, and easy to audit.
- Add tests for behavior changes.

## Pull Requests

Before opening a pull request, run:

```bash
python3 -m pytest
git diff --check
```
