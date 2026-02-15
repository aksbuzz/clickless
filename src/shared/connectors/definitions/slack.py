from src.shared.connectors.models import Connector, TriggerDefinition, ActionDefinition
from src.shared.connectors.registry import registry

slack_connector = Connector(
    id="slack",
    name="Slack",
    description="Send messages and receive events from Slack.",
    triggers=[
        TriggerDefinition(
            id="slack_message_received",
            name="Message Received",
            description="Triggers when a message is posted in a Slack channel.",
            config_schema={
                "type": "object",
                "properties": {
                    "signing_secret": {"type": "string", "title": "Signing Secret", "description": "Slack app signing secret for request verification"},
                    "channel": {"type": "string", "title": "Channel ID", "description": "Optional: only trigger for messages in this channel"},
                    "team_id": {"type": "string", "title": "Team ID", "description": "Optional: only trigger for this Slack workspace"},
                },
            },
        ),
    ],
    actions=[
        ActionDefinition(
            id="slack_send_message",
            name="Send Slack Message",
            description="Posts a message to a Slack channel using an Incoming Webhook URL.",
            config_schema={
                "type": "object",
                "properties": {
                    "webhook_url": {"type": "string", "title": "Webhook URL", "description": "Slack Incoming Webhook URL"},
                    "text": {"type": "string", "title": "Message Text", "description": "Message body. Supports {{field.path}} templates."},
                    "channel": {"type": "string", "title": "Channel Override", "description": "Optional channel override (e.g., #alerts)"},
                    "username": {"type": "string", "title": "Username Override", "description": "Optional display name override"},
                },
                "required": ["webhook_url", "text"],
            },
        ),
    ],
)

registry.register(slack_connector)
