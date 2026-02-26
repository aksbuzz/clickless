from src.shared.connectors.models import Connector, ActionDefinition
from src.shared.connectors.registry import registry

internal_connector = Connector(
    id="internal",
    name="Internal",
    description="Built-in utility actions for data transformation, logging, and demo workflows.",
    triggers=[],
    actions=[
        ActionDefinition(
            id="log",
            name="Log Message",
            description="Logs a message with workflow data. Useful for debugging.",
            config_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "title": "Log Message"},
                },
            },
        ),
        ActionDefinition(
            id="transform_data",
            name="Transform Data",
            description="Applies simple key-value transformations to workflow data.",
            config_schema={
                "type": "object",
                "properties": {
                    "set": {
                        "type": "object",
                        "title": "Set Fields",
                        "description": "Key-value pairs to set in workflow data.",
                    },
                    "remove": {
                        "type": "array",
                        "items": {"type": "string"},
                        "title": "Remove Fields",
                        "description": "Field names to remove from workflow data.",
                    },
                },
            },
        ),
    ],
)

registry.register(internal_connector)
