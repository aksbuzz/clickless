from src.shared.connectors.models import Connector, TriggerDefinition, ActionDefinition
from src.shared.connectors.registry import registry

webhook_connector = Connector(
    id="webhook",
    name="Webhook",
    description="Send and receive webhooks.",
    triggers=[
        TriggerDefinition(
            id="webhook_received",
            name="Webhook Received",
            description="Triggers when an incoming webhook is received.",
            config_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "title": "Webhook Path"},
                },
            },
        ),
    ],
    actions=[
        ActionDefinition(
            id="send_webhook",
            name="Send Webhook",
            description="Sends a POST request to a webhook URL with workflow data.",
            config_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "title": "Webhook URL"},
                    "headers": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "title": "Headers",
                    },
                },
                "required": ["url"],
            },
        ),
    ],
)

registry.register(webhook_connector)
