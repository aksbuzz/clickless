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
        ActionDefinition(
            id="fetch_invoice",
            name="Fetch Invoice",
            description="Demo action: simulates fetching an invoice from an external system.",
            config_schema={},
        ),
        ActionDefinition(
            id="validate_invoice",
            name="Validate Invoice",
            description="Demo action: validates invoice amount (succeeds if amount > 1000).",
            config_schema={},
        ),
        ActionDefinition(
            id="generate_report",
            name="Generate Report",
            description="Demo action: generates a text report from invoice data.",
            config_schema={},
        ),
        ActionDefinition(
            id="archive_report",
            name="Archive Report",
            description="Demo action: simulates archiving a report to S3.",
            config_schema={},
        ),
    ],
)

registry.register(internal_connector)
