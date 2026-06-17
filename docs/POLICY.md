# External Automation Policy

Version: 0.1.0a2
Last updated: 2026-06-17

Voice Memo Hub keeps site-specific automation policy outside the publishable app.

The app can load and evaluate policy, but local workflow rules, notification
destinations, host paths, tokens, and allowlists belong in runtime config.

## Default Path

```text
~/Library/Application Support/voice-memo-hub/config/policy.json
```

Override with:

```bash
VOICE_MEMO_HUB_POLICY=/path/to/policy.json memo policy --show
```

## Repo Boundary

Committed:

- generic policy loader
- policy validation
- disabled example policy
- documentation

Not committed:

- service-specific notification settings
- local allowlists
- host-specific runner paths
- external-system credentials
- runtime decisions or execution logs

## Inspecting Policy

```bash
memo policy
memo policy --show
memo policy --check <action_id>
```

`--check` only evaluates the policy decision. It does not execute the action.

## Rule Modes

- `manual`: keep in inbox.
- `approval_required`: can be executed only after explicit approval.
- `auto`: eligible for future automatic execution by a narrow runner.

## Recommended Policy Tiers

Use these as the default boundary for voice-driven work:

| Tier | Mode | Scope |
| --- | --- | --- |
| 0 | `auto` | Ingest, transcription, indexing, classification, and other app-internal processing. |
| 1 | `auto` | Local DB updates, local outbox files, fixed-template local notifications. |
| 2 | `approval_required` | Read-only live checks, repo verification, and prepared Codex task handoff. |
| 3 | `manual` | Commits, pushes, deploys, public posts, email, work-system writes, device control, deletes, secrets, and config changes. |

The example policy encodes generic practical categories:

1. Notification handling.
2. Reference capture.
3. Codex task preparation.
4. Read-only live checks.
5. Local repo verification.
6. Reusable local tool configuration updates.
7. Local system state/control split.
8. Public or external writes.

## Safe Dispatcher

The `automate` command runs only narrow action types:

- `mark_reviewed`: local database status update.
- `prepare_codex_task`: writes a prompt file under runtime `outbox/`.
- `local_notification`: fixed-template macOS notification.

Unsupported action types are skipped. Policy runs are recorded in
`workflow_runs`, and a given rule/action pair is not repeated after a completed
or skipped run.

```bash
memo automate --dry-run
memo automate
memo run-once --transcribe --apply-policy
```

`approval_required` rules run only when the action candidate has already been
approved. Use `--no-approved` to disable that behavior for a run.

External notification providers and other service-specific actions should be
implemented outside this repo until a generic plugin interface exists.
