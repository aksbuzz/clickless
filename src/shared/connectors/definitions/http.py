from src.shared.connectors.models import Connector, TriggerDefinition, ActionDefinition
from src.shared.connectors.registry import registry

http_connector = Connector(
    id="http",
    name="HTTP",
    description="Make HTTP requests and receive HTTP triggers.",
    triggers=[
        TriggerDefinition(
            id="http_request_received",
            name="HTTP Request Received",
            description="Triggers when an HTTP request is received at the workflow endpoint.",
            config_schema={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                        "default": "POST",
                        "title": "HTTP Method",
                    },
                },
            },
        ),
    ],
    actions=[
        ActionDefinition(
            id="http_request",
            name="Send HTTP Request",
            description="Sends an HTTP request to a specified URL.",
            config_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "title": "URL"},
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                        "default": "GET",
                        "title": "HTTP Method",
                    },
                    "headers": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "title": "Headers",
                    },
                    "body": {"type": "object", "title": "Request Body"},
                },
                "required": ["url", "method"],
            },
        ),
    ],
)

registry.register(http_connector)
