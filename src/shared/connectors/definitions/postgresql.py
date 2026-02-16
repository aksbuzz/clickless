from src.shared.connectors.models import Connector, ActionDefinition
from src.shared.connectors.registry import registry

postgresql_connector = Connector(
    id="postgresql",
    name="PostgreSQL",
    description="Execute queries and commands against a PostgreSQL database.",
    connection_schema={
        "type": "object",
        "properties": {
            "connection_string": {"type": "string", "title": "Connection String", "description": "PostgreSQL connection URI (e.g., postgresql://user:pass@host:5432/db)"},
        },
        "required": ["connection_string"],
    },
    triggers=[],
    actions=[
        ActionDefinition(
            id="postgresql_query",
            name="PostgreSQL Query",
            description="Executes a SELECT query and stores the result rows in workflow data.",
            config_schema={
                "type": "object",
                "properties": {
                    "connection_string": {"type": "string", "title": "Connection String", "description": "PostgreSQL connection URI (e.g., postgresql://user:pass@host:5432/db)"},
                    "query": {"type": "string", "title": "SQL Query", "description": "SELECT query to execute. Use $1, $2 for parameters."},
                    "params": {
                        "type": "array",
                        "title": "Query Parameters",
                        "description": "Positional parameters for the query (prevents SQL injection)",
                    },
                },
                "required": ["connection_string", "query"],
            },
        ),
        ActionDefinition(
            id="postgresql_execute",
            name="PostgreSQL Execute",
            description="Executes an INSERT, UPDATE, or DELETE statement.",
            config_schema={
                "type": "object",
                "properties": {
                    "connection_string": {"type": "string", "title": "Connection String", "description": "PostgreSQL connection URI"},
                    "query": {"type": "string", "title": "SQL Statement", "description": "INSERT/UPDATE/DELETE statement. Use $1, $2 for parameters."},
                    "params": {
                        "type": "array",
                        "title": "Query Parameters",
                        "description": "Positional parameters for the statement",
                    },
                },
                "required": ["connection_string", "query"],
            },
        ),
    ],
)

registry.register(postgresql_connector)
