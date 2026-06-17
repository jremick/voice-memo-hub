from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .actions import (
    list_action_candidates,
    prepare_codex_task,
    update_action_status,
)
from .policy import PolicyDecision, evaluate_action
from .store import connect


AUTO_SAFE_ACTION_TYPES = {
    "mark_reviewed",
    "prepare_codex_task",
    "local_notification",
}


@dataclass(frozen=True)
class AutomationResult:
    action_id: int
    rule_id: Optional[str]
    mode: str
    action_type: Optional[str]
    status: str
    message: str
    output_path: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "action_id": self.action_id,
            "rule_id": self.rule_id,
            "mode": self.mode,
            "action_type": self.action_type,
            "status": self.status,
            "message": self.message,
        }
        if self.output_path:
            payload["output_path"] = self.output_path
        return payload


def render_template(template: str, action: dict[str, Any]) -> str:
    values = {
        "action_id": action.get("id"),
        "recording_id": action.get("recording_id"),
        "kind": action.get("kind"),
        "status": action.get("status"),
        "title": action.get("title"),
        "recorded_at": action.get("recorded_at"),
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", "" if value is None else str(value))
    return rendered


def record_policy_run(
    db_path: Path,
    action_id: int,
    rule_id: str,
    status: str,
    result: dict[str, Any],
) -> int:
    runner = f"policy:{rule_id}"
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO workflow_runs (
              action_candidate_id, runner, status, finished_at, result_json
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            """,
            (action_id, runner, status, json.dumps(result, sort_keys=True)),
        )
        conn.commit()
        return int(cursor.lastrowid)


def policy_run_exists(db_path: Path, action_id: int, rule_id: str) -> bool:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM workflow_runs
            WHERE action_candidate_id = ?
              AND runner = ?
              AND status IN ('done', 'skipped')
            LIMIT 1
            """,
            (action_id, f"policy:{rule_id}"),
        ).fetchone()
    return row is not None


def send_local_notification(title: str, message: str) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("local_notification is only supported on macOS")

    def applescript_string(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    script = (
        "display notification "
        f"{applescript_string(message)} "
        "with title "
        f"{applescript_string(title)}"
    )
    subprocess.run(["osascript", "-e", script], check=True)


def execute_policy_action(
    db_path: Path,
    runtime_dir: Path,
    policy_rule: dict[str, Any],
    action: dict[str, Any],
    decision: PolicyDecision,
    dry_run: bool,
) -> AutomationResult:
    rule_id = decision.rule_id
    action_type = decision.action_type
    if not rule_id or not action_type:
        return AutomationResult(action["id"], rule_id, decision.mode, action_type, "skipped", decision.reason)
    if action_type not in AUTO_SAFE_ACTION_TYPES:
        return AutomationResult(
            action["id"],
            rule_id,
            decision.mode,
            action_type,
            "skipped",
            f"unsupported or unsafe policy action type: {action_type}",
        )
    if policy_run_exists(db_path, action["id"], rule_id):
        return AutomationResult(action["id"], rule_id, decision.mode, action_type, "skipped", "policy already ran")

    action_config = policy_rule.get("action", {})
    template = action_config.get("template") or "Voice Memo Hub handled action {action_id}."
    title = action_config.get("title") or "Voice Memo Hub"
    message = render_template(template, action)

    if dry_run:
        return AutomationResult(action["id"], rule_id, decision.mode, action_type, "dry_run", message)

    if action_type == "mark_reviewed":
        update_action_status(db_path, action["id"], "reviewed", f"auto policy {rule_id}: {decision.reason}")
        record_policy_run(db_path, action["id"], rule_id, "done", {"message": message})
        return AutomationResult(action["id"], rule_id, decision.mode, action_type, "done", "marked reviewed")

    if action_type == "prepare_codex_task":
        outbox = runtime_dir / "outbox" / "codex_tasks"
        outbox.mkdir(parents=True, exist_ok=True)
        output_path = outbox / f"action-{action['id']}.md"
        output_path.write_text(prepare_codex_task(db_path, action["id"]), encoding="utf-8")
        record_policy_run(db_path, action["id"], rule_id, "done", {"output_path": str(output_path)})
        return AutomationResult(
            action["id"],
            rule_id,
            decision.mode,
            action_type,
            "done",
            "prepared Codex task",
            str(output_path),
        )

    if action_type == "local_notification":
        send_local_notification(title, message)
        record_policy_run(db_path, action["id"], rule_id, "done", {"title": title, "message": message})
        return AutomationResult(action["id"], rule_id, decision.mode, action_type, "done", "sent local notification")

    return AutomationResult(action["id"], rule_id, decision.mode, action_type, "skipped", "not implemented")


def run_policy_automation(
    db_path: Path,
    runtime_dir: Path,
    policy: dict[str, Any],
    limit: int = 20,
    dry_run: bool = False,
    include_approved: bool = True,
) -> list[AutomationResult]:
    rules_by_id = {
        rule["id"]: rule
        for rule in policy.get("rules", [])
        if isinstance(rule, dict) and rule.get("id")
    }
    results: list[AutomationResult] = []
    for action in list_action_candidates(db_path, None, limit):
        decision = evaluate_action(policy, action)
        should_run = decision.mode == "auto" or (
            include_approved and decision.mode == "approval_required" and action.get("status") == "approved"
        )
        if not should_run:
            continue
        rule = rules_by_id.get(decision.rule_id or "")
        if not rule:
            continue
        try:
            results.append(execute_policy_action(db_path, runtime_dir, rule, action, decision, dry_run))
        except Exception as exc:  # noqa: BLE001 - policy runner should report per-action failures.
            if decision.rule_id:
                record_policy_run(db_path, action["id"], decision.rule_id, "failed", {"error": str(exc)})
            results.append(
                AutomationResult(
                    action["id"],
                    decision.rule_id,
                    decision.mode,
                    decision.action_type,
                    "failed",
                    str(exc),
                )
            )
    return results
