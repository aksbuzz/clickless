from src.shared.connectors.models import Connector, TriggerDefinition, ActionDefinition
from src.shared.connectors.registry import registry

github_connector = Connector(
    id="github",
    name="GitHub",
    description="Create issues, add comments, and receive webhook events from GitHub.",
    triggers=[
        TriggerDefinition(
            id="github_issue_opened",
            name="Issue Opened",
            description="Triggers when a new issue is opened in a GitHub repository.",
            config_schema={
                "type": "object",
                "properties": {
                    "webhook_secret": {"type": "string", "title": "Webhook Secret", "description": "Optional secret for HMAC signature verification"},
                    "repository": {"type": "string", "title": "Repository", "description": "Filter by repository (owner/repo format)"},
                },
            },
        ),
        TriggerDefinition(
            id="github_push_received",
            name="Push Received",
            description="Triggers when code is pushed to a GitHub repository.",
            config_schema={
                "type": "object",
                "properties": {
                    "webhook_secret": {"type": "string", "title": "Webhook Secret"},
                    "repository": {"type": "string", "title": "Repository", "description": "Filter by repository (owner/repo format)"},
                    "branch": {"type": "string", "title": "Branch", "description": "Optional: only trigger for pushes to this branch"},
                },
            },
        ),
        TriggerDefinition(
            id="github_pr_opened",
            name="Pull Request Opened",
            description="Triggers when a pull request is opened in a GitHub repository.",
            config_schema={
                "type": "object",
                "properties": {
                    "webhook_secret": {"type": "string", "title": "Webhook Secret"},
                    "repository": {"type": "string", "title": "Repository", "description": "Filter by repository (owner/repo format)"},
                },
            },
        ),
    ],
    actions=[
        ActionDefinition(
            id="github_create_issue",
            name="Create GitHub Issue",
            description="Creates a new issue in a GitHub repository.",
            config_schema={
                "type": "object",
                "properties": {
                    "token": {"type": "string", "title": "Personal Access Token"},
                    "owner": {"type": "string", "title": "Repository Owner"},
                    "repo": {"type": "string", "title": "Repository Name"},
                    "title": {"type": "string", "title": "Issue Title", "description": "Supports {{field.path}} templates"},
                    "body": {"type": "string", "title": "Issue Body", "description": "Supports {{field.path}} templates"},
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "title": "Labels",
                        "description": "List of label names to apply",
                    },
                },
                "required": ["token", "owner", "repo", "title"],
            },
        ),
        ActionDefinition(
            id="github_add_comment",
            name="Add GitHub Comment",
            description="Adds a comment to an existing GitHub issue or pull request.",
            config_schema={
                "type": "object",
                "properties": {
                    "token": {"type": "string", "title": "Personal Access Token"},
                    "owner": {"type": "string", "title": "Repository Owner"},
                    "repo": {"type": "string", "title": "Repository Name"},
                    "issue_number": {"type": "integer", "title": "Issue / PR Number"},
                    "body": {"type": "string", "title": "Comment Body", "description": "Supports {{field.path}} templates"},
                },
                "required": ["token", "owner", "repo", "issue_number", "body"],
            },
        ),
    ],
)

registry.register(github_connector)
