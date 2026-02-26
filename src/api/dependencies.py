from functools import lru_cache

from src.api.service import WorkflowManagementService
from src.shared.connectors.registry import registry as connector_registry
import src.shared.connectors.definitions  # noqa: F401 — registers connectors on import
from src.shared.triggers.registry import TriggerHandlerRegistry
from src.api.trigger_handlers.github import GitHubTriggerHandler
from src.api.trigger_handlers.slack import SlackTriggerHandler
from src.api.trigger_handlers.trello import TrelloTriggerHandler


@lru_cache
def get_service() -> WorkflowManagementService:
    return WorkflowManagementService(connector_registry)


@lru_cache
def get_trigger_registry() -> TriggerHandlerRegistry:
    registry = TriggerHandlerRegistry()
    registry.register("github", GitHubTriggerHandler())
    registry.register("slack", SlackTriggerHandler())
    registry.register("trello", TrelloTriggerHandler())
    return registry
