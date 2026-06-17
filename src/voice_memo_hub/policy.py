from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


POLICY_ENV = "VOICE_MEMO_HUB_POLICY"


@dataclass(frozen=True)
class PolicyDecision:
    rule_id: Optional[str]
    mode: str
    action_type: Optional[str]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "mode": self.mode,
            "action_type": self.action_type,
            "reason": self.reason,
        }


def default_policy_path(runtime_dir: Path) -> Path:
    override = os.environ.get(POLICY_ENV)
    if override:
        return Path(override).expanduser()
    return runtime_dir / "config" / "policy.json"


def default_policy() -> dict[str, Any]:
    return {
        "version": 1,
        "rules": [],
    }


def load_policy(runtime_dir: Path) -> tuple[dict[str, Any], Path, bool]:
    path = default_policy_path(runtime_dir)
    if not path.exists():
        return default_policy(), path, False
    with path.open("r", encoding="utf-8") as handle:
        policy = json.load(handle)
    validate_policy(policy)
    return policy, path, True


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("version") != 1:
        raise ValueError("Policy version must be 1")
    rules = policy.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Policy rules must be a list")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"Policy rule {index} must be an object")
        if not rule.get("id"):
            raise ValueError(f"Policy rule {index} is missing id")
        if rule.get("mode") not in {"manual", "approval_required", "auto"}:
            raise ValueError(f"Policy rule {rule.get('id')} has unsupported mode")
        if "match" not in rule or not isinstance(rule["match"], dict):
            raise ValueError(f"Policy rule {rule.get('id')} is missing match object")
        if "action" not in rule or not isinstance(rule["action"], dict):
            raise ValueError(f"Policy rule {rule.get('id')} is missing action object")


def rule_matches(rule: dict[str, Any], action: dict[str, Any]) -> bool:
    match = rule.get("match") or {}
    kind = match.get("kind")
    if kind and action.get("kind") != kind:
        return False

    statuses = match.get("statuses")
    if statuses and action.get("status") not in statuses:
        return False

    text = f"{action.get('title') or ''}\n{action.get('details') or ''}".lower()

    contains_any = [str(item).lower() for item in match.get("contains_any", [])]
    if contains_any and not any(item in text for item in contains_any):
        return False

    contains_all = [str(item).lower() for item in match.get("contains_all", [])]
    if contains_all and not all(item in text for item in contains_all):
        return False

    return True


def evaluate_action(policy: dict[str, Any], action: dict[str, Any]) -> PolicyDecision:
    validate_policy(policy)
    for rule in policy.get("rules", []):
        if not rule.get("enabled", False):
            continue
        if not rule_matches(rule, action):
            continue
        return PolicyDecision(
            rule_id=rule["id"],
            mode=rule["mode"],
            action_type=rule.get("action", {}).get("type"),
            reason=rule.get("reason", "matched policy rule"),
        )
    return PolicyDecision(
        rule_id=None,
        mode="manual",
        action_type=None,
        reason="no enabled policy rule matched",
    )
