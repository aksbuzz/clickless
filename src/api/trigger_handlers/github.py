import hashlib
import hmac
import json
from typing import Any, Dict, List

from src.shared.logging_config import log
from src.shared.triggers.models import TriggerEvent, TriggerValidationResult
from src.shared.triggers.ports import TriggerHandlerPort

GITHUB_EVENT_MAP = {
    "push": "github_push_received",
    "issues": "github_issue_opened",
    "pull_request": "github_pr_opened",
}


class GitHubTriggerHandler(TriggerHandlerPort):

    def validate_webhook(self, headers: Dict[str, str], body: bytes, config: Dict[str, Any]) -> TriggerValidationResult:
        webhook_secret = config.get("webhook_secret")
        if not webhook_secret:
            return TriggerValidationResult(is_valid=True)

        signature_header = headers.get("x-hub-signature-256", "")
        if not signature_header:
            return TriggerValidationResult(is_valid=False, error_message="Missing X-Hub-Signature-256 header")

        expected_sig = "sha256=" + hmac.new(
            webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, signature_header):
            return TriggerValidationResult(is_valid=False, error_message="Invalid signature")

        return TriggerValidationResult(is_valid=True)

    def parse_events(self, headers: Dict[str, str], body: bytes) -> List[TriggerEvent]:
        event_type = headers.get("x-github-event", "")
        payload = json.loads(body)

        if event_type == "ping":
            log.info("GitHub ping received", zen=payload.get("zen"))
            return []

        trigger_id = GITHUB_EVENT_MAP.get(event_type)
        if not trigger_id:
            log.info("Ignoring unmapped GitHub event", event_type=event_type)
            return []

        repo_info = {
            "full_name": payload["repository"]["full_name"],
            "owner": payload["repository"]["owner"]["login"],
            "name": payload["repository"]["name"],
        }

        if event_type == "issues":
            if payload.get("action") != "opened":
                return []
            issue = payload["issue"]
            data = {
                "issue": {
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": issue.get("body", ""),
                    "url": issue["html_url"],
                    "user": issue["user"]["login"],
                    "labels": [l["name"] for l in issue.get("labels", [])],
                },
                "repository": repo_info,
                "sender": payload["sender"]["login"],
            }

        elif event_type == "pull_request":
            if payload.get("action") != "opened":
                return []
            pr = payload["pull_request"]
            data = {
                "pull_request": {
                    "number": pr["number"],
                    "title": pr["title"],
                    "body": pr.get("body", ""),
                    "url": pr["html_url"],
                    "user": pr["user"]["login"],
                    "head_branch": pr["head"]["ref"],
                    "base_branch": pr["base"]["ref"],
                },
                "repository": repo_info,
                "sender": payload["sender"]["login"],
            }

        elif event_type == "push":
            data = {
                "push": {
                    "ref": payload["ref"],
                    "before": payload.get("before", ""),
                    "after": payload.get("after", ""),
                    "commits": [
                        {"id": c["id"], "message": c["message"], "author": c["author"]["name"], "url": c["url"]}
                        for c in payload.get("commits", [])
                    ],
                    "pusher": payload["pusher"]["name"],
                },
                "repository": repo_info,
            }
        else:
            return []

        return [TriggerEvent(
            connector_id="github",
            trigger_id=trigger_id,
            source_event_type=event_type,
            data=data,
            metadata={"repository": payload["repository"]["full_name"]},
        )]

    def matches_workflow_config(self, event: TriggerEvent, workflow_trigger_config: Dict[str, Any]) -> bool:
        config_repo = workflow_trigger_config.get("repository")
        if config_repo:
            event_repo = event.metadata.get("repository", "")
            if config_repo.lower() != event_repo.lower():
                return False

        config_branch = workflow_trigger_config.get("branch")
        if config_branch and event.trigger_id == "github_push_received":
            push_ref = event.data.get("push", {}).get("ref", "")
            if not push_ref.endswith(f"/{config_branch}"):
                return False

        return True
