from src.shared.connectors.models import Connector, TriggerDefinition, ActionDefinition
from src.shared.connectors.registry import registry

trello_connector = Connector(
    id="trello",
    name="Trello",
    description="Create cards, add comments, and receive webhook events from Trello.",
    connection_schema={
        "type": "object",
        "properties": {
            "api_key": {"type": "string", "title": "API Key"},
            "api_token": {"type": "string", "title": "API Token"},
        },
        "required": ["api_key", "api_token"],
    },
    triggers=[
        TriggerDefinition(
            id="trello_card_created",
            name="Card Created",
            description="Triggers when a new card is created on a Trello board.",
            config_schema={
                "type": "object",
                "properties": {
                    "board_id": {"type": "string", "title": "Board ID", "description": "Optional: only trigger for this board"},
                    "list_id": {"type": "string", "title": "List ID", "description": "Optional: only trigger for cards in this list"},
                },
            },
        ),
        TriggerDefinition(
            id="trello_card_moved",
            name="Card Moved",
            description="Triggers when a card is moved to a different list.",
            config_schema={
                "type": "object",
                "properties": {
                    "board_id": {"type": "string", "title": "Board ID", "description": "Optional: only trigger for this board"},
                    "list_id": {"type": "string", "title": "Target List ID", "description": "Optional: only trigger when card is moved TO this list"},
                },
            },
        ),
    ],
    actions=[
        ActionDefinition(
            id="trello_create_card",
            name="Create Trello Card",
            description="Creates a new card on a Trello board.",
            config_schema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string", "title": "API Key"},
                    "api_token": {"type": "string", "title": "API Token"},
                    "list_id": {"type": "string", "title": "List ID", "description": "The ID of the Trello list to add the card to"},
                    "name": {"type": "string", "title": "Card Name", "description": "Supports {{field.path}} templates"},
                    "description": {"type": "string", "title": "Card Description", "description": "Supports {{field.path}} templates"},
                },
                "required": ["api_key", "api_token", "list_id", "name"],
            },
        ),
        ActionDefinition(
            id="trello_add_comment",
            name="Add Trello Comment",
            description="Adds a comment to an existing Trello card.",
            config_schema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string", "title": "API Key"},
                    "api_token": {"type": "string", "title": "API Token"},
                    "card_id": {"type": "string", "title": "Card ID", "description": "The ID of the card to comment on. Supports {{field.path}} templates."},
                    "text": {"type": "string", "title": "Comment Text", "description": "Supports {{field.path}} templates"},
                },
                "required": ["api_key", "api_token", "card_id", "text"],
            },
        ),
    ],
)

registry.register(trello_connector)
