from __future__ import annotations

from voice_memo_hub.policy import default_policy, evaluate_action, validate_policy


def test_default_policy_requires_manual_review() -> None:
    action = {
        "kind": "codex_request_candidate",
        "status": "candidate",
        "title": "Notify me",
        "details": "Send me a notification when this works.",
    }

    decision = evaluate_action(default_policy(), action)

    assert decision.mode == "manual"
    assert decision.rule_id is None


def test_enabled_policy_rule_can_match_without_site_specific_details() -> None:
    policy = {
        "version": 1,
        "rules": [
            {
                "id": "notify-review",
                "enabled": True,
                "mode": "approval_required",
                "reason": "notification request matched",
                "match": {
                    "kind": "codex_request_candidate",
                    "statuses": ["candidate"],
                    "contains_all": ["notify"],
                },
                "action": {"type": "local_notification"},
            }
        ],
    }
    action = {
        "kind": "codex_request_candidate",
        "status": "candidate",
        "title": "Notify me",
        "details": "Notify me when this works.",
    }

    validate_policy(policy)
    decision = evaluate_action(policy, action)

    assert decision.rule_id == "notify-review"
    assert decision.mode == "approval_required"
    assert decision.action_type == "local_notification"


def test_notification_does_not_match_git_push_manual_rule() -> None:
    policy = {
        "version": 1,
        "rules": [
            {
                "id": "manual-external-writes",
                "enabled": True,
                "mode": "manual",
                "reason": "external writes stay manual",
                "match": {"contains_any": ["git push", "deploy"]},
                "action": {"type": "manual_review"},
            },
            {
                "id": "local-notify",
                "enabled": True,
                "mode": "auto",
                "reason": "fixed local notification",
                "match": {"contains_any": ["notification"]},
                "action": {"type": "local_notification"},
            },
        ],
    }
    action = {
        "kind": "codex_request_candidate",
        "status": "candidate",
        "title": "Send notification",
        "details": "Send me a notification when transcription works.",
    }

    decision = evaluate_action(policy, action)

    assert decision.rule_id == "local-notify"
    assert decision.mode == "auto"


def test_notification_reference_can_be_guarded_before_auto_reference() -> None:
    policy = {
        "version": 1,
        "rules": [
            {
                "id": "review-reference-notification",
                "enabled": True,
                "mode": "approval_required",
                "reason": "possible misclassification",
                "match": {"kind": "reference", "contains_any": ["notification"]},
                "action": {"type": "local_notification"},
            },
            {
                "id": "auto-reference-review",
                "enabled": True,
                "mode": "auto",
                "reason": "plain reference",
                "match": {"kind": "reference"},
                "action": {"type": "mark_reviewed"},
            },
        ],
    }
    action = {
        "kind": "reference",
        "status": "candidate",
        "title": "Notification",
        "details": "Send me a notification.",
    }

    decision = evaluate_action(policy, action)

    assert decision.rule_id == "review-reference-notification"
    assert decision.mode == "approval_required"
