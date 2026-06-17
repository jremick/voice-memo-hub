from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .actions import (
    extract_action_candidates,
    list_action_candidates,
    prepare_codex_task,
    record_dispatch,
    update_action_status,
)
from .automation import run_policy_automation
from .ingest import ingest
from .paths import db_path, default_runtime_dir, default_source_dir, ensure_runtime_dirs
from .policy import evaluate_action, load_policy
from .queries import digest, recording_detail, search_transcripts
from .store import connect, init_db
from .transcribe import DEFAULT_MODEL, store_transcript, transcribe_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memo", description="Voice Memo Hub CLI")
    parser.add_argument("--runtime-dir", type=Path, default=default_runtime_dir())
    parser.add_argument("--source-dir", type=Path, default=default_source_dir())
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check paths and database readiness")
    sub.add_parser("init", help="Create runtime directories and database")
    sub.add_parser("ingest", help="Ingest new Voice Memos")

    list_parser = sub.add_parser("list", help="List recordings")
    list_parser.add_argument("--limit", type=int, default=20)

    search = sub.add_parser("search", help="Search transcript text")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)

    show = sub.add_parser("show", help="Show one recording")
    show.add_argument("recording_id")

    transcribe = sub.add_parser("transcribe", help="Transcribe recordings locally")
    transcribe.add_argument("recording_id", nargs="?")
    transcribe.add_argument("--pending", action="store_true")
    transcribe.add_argument("--model", default=DEFAULT_MODEL)
    transcribe.add_argument("--limit", type=int)
    transcribe.add_argument("--max-duration-seconds", type=float)
    transcribe.add_argument("--newest-first", action="store_true")
    transcribe.add_argument("--retry-incomplete", action="store_true")

    actions = sub.add_parser("actions", help="List or extract action candidates")
    actions.add_argument("--extract", action="store_true")
    actions.add_argument("--limit", type=int, default=20)
    actions.add_argument("--status")

    inbox = sub.add_parser("inbox", help="List candidate and approved actions for Codex review")
    inbox.add_argument("--limit", type=int, default=20)

    approve = sub.add_parser("approve", help="Approve an action candidate")
    approve.add_argument("action_id", type=int)
    approve.add_argument("--note")

    reject = sub.add_parser("reject", help="Reject an action candidate")
    reject.add_argument("action_id", type=int)
    reject.add_argument("--note")

    reviewed = sub.add_parser("reviewed", help="Mark an action candidate reviewed")
    reviewed.add_argument("action_id", type=int)
    reviewed.add_argument("--note")

    prepare_task = sub.add_parser("prepare-codex-task", help="Render a safe Codex task prompt")
    prepare_task.add_argument("action_id", type=int)

    dispatch = sub.add_parser("dispatch", help="Record dispatch of an approved action")
    dispatch.add_argument("action_id", type=int)
    dispatch.add_argument("--runner", default="codex")
    dispatch.add_argument("--note")

    digest_parser = sub.add_parser("digest", help="Render a Markdown digest")
    digest_parser.add_argument("--limit", type=int, default=10)

    policy = sub.add_parser("policy", help="Inspect external automation policy")
    policy.add_argument("--show", action="store_true")
    policy.add_argument("--check", type=int, metavar="ACTION_ID")

    automate = sub.add_parser("automate", help="Run narrow safe actions from external policy")
    automate.add_argument("--limit", type=int, default=20)
    automate.add_argument("--dry-run", action="store_true")
    automate.add_argument(
        "--no-approved",
        action="store_true",
        help="Do not run approval_required rules even when the action is approved",
    )

    run_once = sub.add_parser("run-once", help="Run one ingest/transcribe/extract pass")
    run_once.add_argument("--transcribe", action="store_true")
    run_once.add_argument("--model", default=DEFAULT_MODEL)
    run_once.add_argument("--limit", type=int, default=2)
    run_once.add_argument("--max-duration-seconds", type=float, default=1800)
    run_once.add_argument("--newest-first", action="store_true", default=True)
    run_once.add_argument("--retry-incomplete", action="store_true")
    run_once.add_argument("--apply-policy", action="store_true")
    run_once.add_argument("--policy-dry-run", action="store_true")

    return parser


def prepare(runtime_dir: Path) -> Path:
    ensure_runtime_dirs(runtime_dir)
    path = db_path(runtime_dir)
    init_db(path)
    return path


def cmd_doctor(args: argparse.Namespace) -> int:
    runtime = args.runtime_dir.expanduser()
    source = args.source_dir.expanduser()
    path = prepare(runtime)
    print(json.dumps({
        "runtime_dir": str(runtime),
        "source_dir": str(source),
        "source_exists": source.exists(),
        "source_db_exists": (source / "CloudRecordings.db").exists(),
        "db_path": str(path),
        "db_exists": path.exists(),
    }, indent=2))
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    runtime = args.runtime_dir.expanduser()
    source = args.source_dir.expanduser()
    path = prepare(runtime)
    print(json.dumps(ingest(source, runtime, path), indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    path = prepare(args.runtime_dir.expanduser())
    with connect(path) as conn:
        rows = conn.execute(
            """
            SELECT id, recorded_at, duration_seconds, transcript_status, source_path
            FROM recordings ORDER BY recorded_at DESC LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
    for row in rows:
        print(f"{row['id']}  {row['recorded_at']}  {row['duration_seconds']:.3f}s  {row['transcript_status']}  {row['source_path']}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    path = prepare(args.runtime_dir.expanduser())
    rows = search_transcripts(path, args.query, args.limit)
    for row in rows:
        print(f"{row['id']}  {row['recorded_at']}  {row['snippet']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    path = prepare(args.runtime_dir.expanduser())
    detail = recording_detail(path, args.recording_id)
    if not detail:
        print(f"Recording not found: {args.recording_id}", file=sys.stderr)
        return 1
    print(json.dumps(detail["recording"], indent=2))
    if detail["transcript"]:
        print("\nTranscript:\n")
        print(detail["transcript"]["text"])
    return 0


def pending_recordings(
    path: Path,
    recording_id: Optional[str],
    pending: bool,
    limit: Optional[int] = None,
    max_duration_seconds: Optional[float] = None,
    newest_first: bool = False,
    retry_incomplete: bool = False,
) -> list[dict]:
    where = []
    params: list[object] = []
    if recording_id:
        where.append("id = ?")
        params.append(recording_id)
    if pending:
        if retry_incomplete:
            where.append("transcript_status IN ('pending', 'empty', 'failed')")
        else:
            where.append("transcript_status = 'pending'")
    if max_duration_seconds is not None:
        where.append("(duration_seconds IS NULL OR duration_seconds <= ?)")
        params.append(max_duration_seconds)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    order = "DESC" if newest_first else "ASC"
    limit_clause = "LIMIT ?" if limit is not None else ""
    if limit is not None:
        params.append(limit)
    with connect(path) as conn:
        return [
            dict(row)
            for row in conn.execute(
                f"SELECT * FROM recordings {clause} ORDER BY recorded_at {order} {limit_clause}",
                params,
            ).fetchall()
        ]


def transcribe_selected(runtime: Path, path: Path, rows: list[dict], model: str) -> int:
    count = 0
    for row in rows:
        audio_path = Path(row["archive_path"])
        try:
            result = transcribe_audio(audio_path, runtime / "audio" / "derived", model)
            store_transcript(path, row["id"], result, model)
            extract_action_candidates(path, row["id"])
            print(f"transcribed {row['id']}: {len((result.get('text') or '').strip())} chars")
            count += 1
        except Exception as exc:  # noqa: BLE001 - CLI should keep moving.
            with connect(path) as conn:
                conn.execute("UPDATE recordings SET transcript_status = 'failed' WHERE id = ?", (row["id"],))
                conn.commit()
            print(f"failed {row['id']}: {exc}", file=sys.stderr)
    return count


def cmd_transcribe(args: argparse.Namespace) -> int:
    runtime = args.runtime_dir.expanduser()
    path = prepare(runtime)
    rows = pending_recordings(
        path,
        args.recording_id,
        args.pending,
        args.limit,
        args.max_duration_seconds,
        args.newest_first,
        args.retry_incomplete,
    )
    transcribe_selected(runtime, path, rows, args.model)
    return 0


def cmd_actions(args: argparse.Namespace) -> int:
    path = prepare(args.runtime_dir.expanduser())
    if args.extract:
        print(f"inserted {extract_action_candidates(path)} action candidates")
    rows = list_action_candidates(path, args.status, args.limit)
    for row in rows:
        print(f"{row['id']}  {row['kind']}  {row['status']}  {row['confidence']}  {row['recording_id']}  {row['title']}")
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    path = prepare(args.runtime_dir.expanduser())
    rows = []
    rows.extend(list_action_candidates(path, "approved", args.limit))
    rows.extend(list_action_candidates(path, "candidate", args.limit))
    for row in rows[: args.limit]:
        print(f"{row['id']}  {row['kind']}  {row['status']}  {row['recorded_at']}  {row['title']}")
    return 0


def cmd_update_action(args: argparse.Namespace, status: str) -> int:
    path = prepare(args.runtime_dir.expanduser())
    action = update_action_status(path, args.action_id, status, args.note)
    print(f"{action['id']}  {action['kind']}  {action['status']}  {action['title']}")
    return 0


def cmd_prepare_codex_task(args: argparse.Namespace) -> int:
    path = prepare(args.runtime_dir.expanduser())
    print(prepare_codex_task(path, args.action_id))
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    path = prepare(args.runtime_dir.expanduser())
    prompt = prepare_codex_task(path, args.action_id)
    run_id = record_dispatch(
        path,
        args.action_id,
        args.runner,
        {"status": "queued", "note": args.note, "prompt_preview": prompt[:500]},
    )
    print(f"workflow_run {run_id} queued for action {args.action_id} via {args.runner}")
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    path = prepare(args.runtime_dir.expanduser())
    print(digest(path, args.limit), end="")
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    runtime = args.runtime_dir.expanduser()
    path = prepare(runtime)
    policy, policy_path, exists = load_policy(runtime)

    if args.check is not None:
        action = next((row for row in list_action_candidates(path, None, 1000) if row["id"] == args.check), None)
        if not action:
            print(f"Action candidate not found: {args.check}", file=sys.stderr)
            return 1
        print(json.dumps(evaluate_action(policy, action).as_dict(), indent=2))
        return 0

    if args.show:
        print(json.dumps(policy, indent=2))
        return 0

    print(json.dumps({
        "path": str(policy_path),
        "exists": exists,
        "rule_count": len(policy.get("rules", [])),
    }, indent=2))
    return 0


def cmd_automate(args: argparse.Namespace) -> int:
    runtime = args.runtime_dir.expanduser()
    path = prepare(runtime)
    policy, policy_path, exists = load_policy(runtime)
    results = run_policy_automation(
        path,
        runtime,
        policy,
        limit=args.limit,
        dry_run=args.dry_run,
        include_approved=not args.no_approved,
    )
    print(json.dumps({
        "policy_path": str(policy_path),
        "policy_exists": exists,
        "dry_run": args.dry_run,
        "results": [result.as_dict() for result in results],
    }, indent=2))
    return 0


def cmd_run_once(args: argparse.Namespace) -> int:
    runtime = args.runtime_dir.expanduser()
    source = args.source_dir.expanduser()
    path = prepare(runtime)
    print(json.dumps(ingest(source, runtime, path), indent=2))
    if args.transcribe:
        rows = pending_recordings(
            path,
            None,
            True,
            args.limit,
            args.max_duration_seconds,
            args.newest_first,
            args.retry_incomplete,
        )
        transcribe_selected(runtime, path, rows, args.model)
    inserted = extract_action_candidates(path)
    print(f"action candidates inserted: {inserted}")
    if args.apply_policy:
        policy, _, _ = load_policy(runtime)
        results = run_policy_automation(
            path,
            runtime,
            policy,
            limit=20,
            dry_run=args.policy_dry_run,
        )
        print(f"policy actions handled: {len(results)}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "doctor": cmd_doctor,
        "init": lambda parsed: 0 if prepare(parsed.runtime_dir.expanduser()) else 1,
        "ingest": cmd_ingest,
        "list": cmd_list,
        "search": cmd_search,
        "show": cmd_show,
        "transcribe": cmd_transcribe,
        "actions": cmd_actions,
        "inbox": cmd_inbox,
        "approve": lambda parsed: cmd_update_action(parsed, "approved"),
        "reject": lambda parsed: cmd_update_action(parsed, "rejected"),
        "reviewed": lambda parsed: cmd_update_action(parsed, "reviewed"),
        "prepare-codex-task": cmd_prepare_codex_task,
        "dispatch": cmd_dispatch,
        "digest": cmd_digest,
        "policy": cmd_policy,
        "automate": cmd_automate,
        "run-once": cmd_run_once,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
