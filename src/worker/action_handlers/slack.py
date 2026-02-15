import httpx

from src.shared.connectors.template import resolve_config
from src.shared.logging_config import log
from src.worker.domain.models import ActionStatus
from src.worker.domain.ports import ActionHandlerPort, ActionResult


class SlackSendMessageHandler(ActionHandlerPort):
    def execute(self, instance_id, data, config=None, **kwargs):
        config = resolve_config(config or {}, data)
        webhook_url = config.get("webhook_url", "")
        text = config.get("text", "")

        if not webhook_url:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'webhook_url' in config")
        if not text:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'text' in config")

        payload = {"text": text}
        if config.get("channel"):
            payload["channel"] = config["channel"]
        if config.get("username"):
            payload["username"] = config["username"]

        log.info("Sending Slack message", instance_id=instance_id, channel=config.get("channel"))
        try:
            response = httpx.post(webhook_url, json=payload, timeout=30)
            data["slack_response"] = {"status_code": response.status_code}
            if response.is_success:
                log.info("Slack message sent", instance_id=instance_id)
                return ActionResult(ActionStatus.SUCCESS, data)
            else:
                return ActionResult(ActionStatus.FAILURE, data, error_message=f"Slack returned HTTP {response.status_code}")
        except httpx.TimeoutException:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Slack webhook timed out")
        except httpx.RequestError as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"Slack request error: {e}")
