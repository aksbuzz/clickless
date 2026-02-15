import json
from typing import Any, Dict, List

from src.shared.logging_config import log
from src.shared.triggers.models import TriggerEvent, TriggerValidationResult
from src.shared.triggers.ports import TriggerHandlerPort


class TrelloTriggerHandler(TriggerHandlerPort):

    def validate_webhook(self, headers: Dict[str, str], body: bytes, config: Dict[str, Any]) -> TriggerValidationResult:
        # Trello verifies callback URLs via HEAD request at registration time.
        # No cryptographic signature on POST events.
        return TriggerValidationResult(is_valid=True)

    def parse_events(self, headers: Dict[str, str], body: bytes) -> List[TriggerEvent]:
        payload = json.loads(body)
        action = payload.get("action", {})
        action_type = action.get("type", "")

        if action_type == "createCard":
            card = action.get("data", {}).get("card", {})
            list_data = action.get("data", {}).get("list", {})
            board = action.get("data", {}).get("board", {})
            data = {
                "card": {"id": card.get("id", ""), "name": card.get("name", ""), "short_link": card.get("shortLink", "")},
                "list": {"id": list_data.get("id", ""), "name": list_data.get("name", "")},
                "board": {"id": board.get("id", ""), "name": board.get("name", "")},
                "member": action.get("memberCreator", {}).get("username", ""),
            }
            return [TriggerEvent(
                connector_id="trello",
                trigger_id="trello_card_created",
                source_event_type=action_type,
                data=data,
                metadata={"board_id": board.get("id", ""), "list_id": list_data.get("id", "")},
            )]

        elif action_type == "updateCard":
            action_data = action.get("data", {})
            if "listAfter" not in action_data:
                log.info("Ignoring updateCard without listAfter")
                return []

            card = action_data.get("card", {})
            board = action_data.get("board", {})
            data = {
                "card": {"id": card.get("id", ""), "name": card.get("name", "")},
                "list_before": {"id": action_data.get("listBefore", {}).get("id", ""), "name": action_data.get("listBefore", {}).get("name", "")},
                "list_after": {"id": action_data["listAfter"].get("id", ""), "name": action_data["listAfter"].get("name", "")},
                "board": {"id": board.get("id", ""), "name": board.get("name", "")},
                "member": action.get("memberCreator", {}).get("username", ""),
            }
            return [TriggerEvent(
                connector_id="trello",
                trigger_id="trello_card_moved",
                source_event_type=action_type,
                data=data,
                metadata={
                    "board_id": board.get("id", ""),
                    "list_after_id": action_data["listAfter"].get("id", ""),
                },
            )]

        else:
            log.info("Ignoring unmapped Trello action type", action_type=action_type)
            return []

    def matches_workflow_config(self, event: TriggerEvent, workflow_trigger_config: Dict[str, Any]) -> bool:
        config_board = workflow_trigger_config.get("board_id")
        if config_board:
            if config_board != event.metadata.get("board_id", ""):
                return False

        config_list = workflow_trigger_config.get("list_id")
        if config_list and event.trigger_id == "trello_card_moved":
            if config_list != event.metadata.get("list_after_id", ""):
                return False

        return True
