import httpx

from src.shared.connectors.template import resolve_config
from src.shared.logging_config import log
from src.worker.domain.models import ActionStatus
from src.worker.domain.ports import ActionHandlerPort, ActionResult

TRELLO_API_BASE = "https://api.trello.com/1"


class TrelloCreateCardHandler(ActionHandlerPort):
    def execute(self, instance_id, data, config=None, **kwargs):
        config = resolve_config(config or {}, data)
        api_key = config.get("api_key", "")
        api_token = config.get("api_token", "")
        list_id = config.get("list_id", "")
        name = config.get("name", "")

        if not all([api_key, api_token, list_id, name]):
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing required Trello config (api_key, api_token, list_id, name)")

        params = {"key": api_key, "token": api_token}
        body = {"idList": list_id, "name": name}
        if config.get("description"):
            body["desc"] = config["description"]

        log.info("Creating Trello card", instance_id=instance_id, list_id=list_id)
        try:
            response = httpx.post(f"{TRELLO_API_BASE}/cards", params=params, json=body, timeout=30)
            if response.is_success:
                card = response.json()
                data["trello_card"] = {"id": card["id"], "url": card.get("url", "")}
                log.info("Trello card created", instance_id=instance_id, card_id=card["id"])
                return ActionResult(ActionStatus.SUCCESS, data)
            else:
                return ActionResult(ActionStatus.FAILURE, data, error_message=f"Trello API returned HTTP {response.status_code}")
        except httpx.TimeoutException:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Trello API timed out")
        except httpx.RequestError as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"Trello request error: {e}")


class TrelloAddCommentHandler(ActionHandlerPort):
    def execute(self, instance_id, data, config=None, **kwargs):
        config = resolve_config(config or {}, data)
        api_key = config.get("api_key", "")
        api_token = config.get("api_token", "")
        card_id = config.get("card_id", "")
        text = config.get("text", "")

        if not all([api_key, api_token, card_id, text]):
            return ActionResult(ActionStatus.FAILURE, data, error_message="Missing required Trello config (api_key, api_token, card_id, text)")

        params = {"key": api_key, "token": api_token}
        body = {"text": text}

        log.info("Adding Trello comment", instance_id=instance_id, card_id=card_id)
        try:
            response = httpx.post(f"{TRELLO_API_BASE}/cards/{card_id}/actions/comments", params=params, json=body, timeout=30)
            if response.is_success:
                comment = response.json()
                data["trello_comment"] = {"id": comment["id"]}
                log.info("Trello comment added", instance_id=instance_id, card_id=card_id)
                return ActionResult(ActionStatus.SUCCESS, data)
            else:
                return ActionResult(ActionStatus.FAILURE, data, error_message=f"Trello API returned HTTP {response.status_code}")
        except httpx.TimeoutException:
            return ActionResult(ActionStatus.FAILURE, data, error_message="Trello API timed out")
        except httpx.RequestError as e:
            return ActionResult(ActionStatus.FAILURE, data, error_message=f"Trello request error: {e}")
