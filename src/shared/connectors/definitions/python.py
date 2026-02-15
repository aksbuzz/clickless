from src.shared.connectors.models import Connector, ActionDefinition
from src.shared.connectors.registry import registry

python_connector = Connector(
    id="python",
    name="Python",
    description="Execute Python code snippets with access to workflow data.",
    triggers=[],
    actions=[
        ActionDefinition(
            id="python_execute",
            name="Execute Python Code",
            description="Runs a Python code snippet. The code receives the workflow 'data' dict and can mutate it. Allowed imports: math, json, re, datetime.",
            config_schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "title": "Python Code", "description": "Python code to execute. Access workflow data via the 'data' variable."},
                    "timeout_seconds": {"type": "integer", "title": "Timeout (seconds)", "default": 30, "minimum": 1, "maximum": 300},
                },
                "required": ["code"],
            },
        ),
    ],
)

registry.register(python_connector)
