import httpx

from src.shared.connectors.template import resolve_config
from src.shared.logging_config import log
from src.worker.domain.models import ActionStatus
from src.worker.domain.ports import ActionHandlerPort, ActionResult

GITHUB_API_BASE = "https://api.github.com"


class GitHubCreateIssueHandler(ActionHandlerPort):
    def execute(self, instance_id, data, config=None, **kwargs):
        config = resolve_config(config or {}, data)
        token = config.get("token", "")
        owner = config.get("owner", "")
        repo = config.get("repo", "")
        title = config.get("title", "")

        if not all([token, owner, repo, title]):
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing required GitHub config (token, owner, repo, title)")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        body = {"title": title}
        if config.get("body"):
            body["body"] = config["body"]
        if config.get("labels"):
            body["labels"] = config["labels"]

        log.info("Creating GitHub issue", instance_id=instance_id, repo=f"{owner}/{repo}")
        try:
            response = httpx.post(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues", headers=headers, json=body, timeout=30)
            if response.is_success:
                issue = response.json()
                data["github_issue"] = {
                    "number": issue["number"],
                    "url": issue["html_url"],
                    "id": issue["id"],
                }
                log.info("GitHub issue created", instance_id=instance_id, issue_number=issue["number"])
                return ActionResult(ActionStatus.SUCCESS, data)
            else:
                return ActionResult(ActionStatus.FAILURE, data, error_message=f"GitHub API returned HTTP {response.status_code}")
        except httpx.TimeoutException:
            return ActionResult(ActionStatus.FAILURE, data, error_message="GitHub API timed out")
        except httpx.RequestError as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"GitHub request error: {e}")


class GitHubAddCommentHandler(ActionHandlerPort):
    def execute(self, instance_id, data, config=None, **kwargs):
        config = resolve_config(config or {}, data)
        token = config.get("token", "")
        owner = config.get("owner", "")
        repo = config.get("repo", "")
        issue_number = config.get("issue_number")
        body_text = config.get("body", "")

        if not all([token, owner, repo, issue_number, body_text]):
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing required GitHub config (token, owner, repo, issue_number, body)")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        log.info("Adding GitHub comment", instance_id=instance_id, repo=f"{owner}/{repo}", issue_number=issue_number)
        try:
            response = httpx.post(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments",
                headers=headers,
                json={"body": body_text},
                timeout=30,
            )
            if response.is_success:
                comment = response.json()
                data["github_comment"] = {"id": comment["id"], "url": comment["html_url"]}
                log.info("GitHub comment added", instance_id=instance_id, comment_id=comment["id"])
                return ActionResult(ActionStatus.SUCCESS, data)
            else:
                return ActionResult(ActionStatus.FAILURE, data, error_message=f"GitHub API returned HTTP {response.status_code}")
        except httpx.TimeoutException:
            return ActionResult(ActionStatus.FAILURE, data, error_message="GitHub API timed out")
        except httpx.RequestError as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"GitHub request error: {e}")
