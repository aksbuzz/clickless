from src.shared.connectors.models import Connector, ActionDefinition
from src.shared.connectors.registry import registry

flow_control_connector = Connector(
    id="flow_control",
    name="Flow Control",
    description="System steps for branching, delays, and waiting for external events.",
    triggers=[],
    actions=[
        ActionDefinition(
            id="branch",
            name="If / Else Branch",
            description="Evaluates a condition and routes to different paths.",
            config_schema={
                "type": "object",
                "properties": {
                    "field": {"type": "string", "title": "Field Path", "description": "Dot-notation path to evaluate (e.g., 'invoice.amount')"},
                    "operator": {"type": "string", "enum": ["eq", "neq", "gt", "gte", "lt", "lte", "contains", "exists"], "title": "Operator"},
                    "value": {"title": "Value", "description": "Value to compare against"},
                },
                "required": ["field", "operator"],
            },
        ),
        ActionDefinition(
            id="delay",
            name="Delay / Wait",
            description="Pauses the workflow for a specified duration.",
            config_schema={
                "type": "object",
                "properties": {
                    "duration_seconds": {"type": "integer", "title": "Duration (seconds)", "minimum": 1},
                },
                "required": ["duration_seconds"],
            },
        ),
        ActionDefinition(
            id="wait_for_event",
            name="Wait for Event",
            description="Pauses the workflow until an external event is received via POST /instances/{id}/events.",
            config_schema={
                "type": "object",
                "properties": {
                    "event_name": {"type": "string", "title": "Event Name", "description": "Descriptive name for the expected event"},
                    "timeout_seconds": {"type": "integer", "title": "Timeout (seconds)", "description": "Optional timeout. Workflow fails if event not received in time."},
                },
            },
        ),
    ],
)

registry.register(flow_control_connector)
