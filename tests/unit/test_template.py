"""Unit tests for template resolution functionality."""
import pytest
from src.shared.connectors.template import (
    resolve_field,
    resolve_template,
    resolve_config,
)


class TestResolveField:
    """Tests for resolve_field function."""

    def test_resolve_simple_field(self):
        """Test resolving a simple top-level field."""
        data = {"name": "John", "age": 30}
        result = resolve_field(data, "name")
        assert result == "John"

    def test_resolve_nested_field(self):
        """Test resolving a nested field with dot notation."""
        data = {"user": {"name": "John", "email": "john@example.com"}}
        result = resolve_field(data, "user.name")
        assert result == "John"

    def test_resolve_deeply_nested_field(self):
        """Test resolving a deeply nested field."""
        data = {
            "invoice": {
                "customer": {
                    "name": "ACME Corp",
                    "id": "123"
                }
            }
        }
        result = resolve_field(data, "invoice.customer.name")
        assert result == "ACME Corp"

    def test_resolve_field_with_whitespace(self):
        """Test resolving field with whitespace in path."""
        data = {"user": {"name": "John"}}
        result = resolve_field(data, " user.name ")
        assert result == "John"

    def test_resolve_nonexistent_field(self):
        """Test resolving a field that doesn't exist."""
        data = {"name": "John"}
        result = resolve_field(data, "email")
        assert result is None

    def test_resolve_nonexistent_nested_field(self):
        """Test resolving a nested field that doesn't exist."""
        data = {"user": {"name": "John"}}
        result = resolve_field(data, "user.email")
        assert result is None

    def test_resolve_field_non_dict_parent(self):
        """Test resolving a field when parent is not a dict."""
        data = {"name": "John"}
        result = resolve_field(data, "name.invalid")
        assert result is None


class TestResolveTemplate:
    """Tests for resolve_template function."""

    def test_resolve_single_placeholder(self):
        """Test resolving a template with a single placeholder."""
        data = {"name": "World"}
        result = resolve_template("Hello {{name}}!", data)
        assert result == "Hello World!"

    def test_resolve_multiple_placeholders(self):
        """Test resolving a template with multiple placeholders."""
        data = {"first": "John", "last": "Doe"}
        result = resolve_template("{{first}} {{last}}", data)
        assert result == "John Doe"

    def test_resolve_nested_placeholder(self):
        """Test resolving a template with nested field placeholder."""
        data = {"user": {"name": "Alice"}}
        result = resolve_template("Welcome {{user.name}}", data)
        assert result == "Welcome Alice"

    def test_resolve_placeholder_with_whitespace(self):
        """Test resolving placeholder with extra whitespace."""
        data = {"name": "Bob"}
        result = resolve_template("Hi {{ name }}", data)
        assert result == "Hi Bob"

    def test_resolve_missing_placeholder(self):
        """Test that missing placeholders are left unchanged."""
        data = {"name": "Alice"}
        result = resolve_template("{{name}} - {{missing}}", data)
        assert result == "Alice - {{missing}}"

    def test_resolve_no_placeholders(self):
        """Test template without placeholders."""
        result = resolve_template("Just plain text", {"any": "data"})
        assert result == "Just plain text"

    def test_resolve_number_value(self):
        """Test resolving placeholder with number value."""
        data = {"count": 42}
        result = resolve_template("Count: {{count}}", data)
        assert result == "Count: 42"

    def test_resolve_boolean_value(self):
        """Test resolving placeholder with boolean value."""
        data = {"active": True}
        result = resolve_template("Active: {{active}}", data)
        assert result == "Active: True"


class TestResolveConfig:
    """Tests for resolve_config function."""

    def test_resolve_simple_string_values(self):
        """Test resolving config with simple string values."""
        config = {
            "message": "Hello {{name}}",
            "subject": "Welcome {{user.name}}"
        }
        data = {"name": "Alice", "user": {"name": "Bob"}}
        result = resolve_config(config, data)

        assert result["message"] == "Hello Alice"
        assert result["subject"] == "Welcome Bob"

    def test_resolve_nested_dict(self):
        """Test resolving config with nested dictionaries."""
        config = {
            "email": {
                "to": "{{user.email}}",
                "subject": "Hello {{user.name}}"
            }
        }
        data = {"user": {"name": "Alice", "email": "alice@example.com"}}
        result = resolve_config(config, data)

        assert result["email"]["to"] == "alice@example.com"
        assert result["email"]["subject"] == "Hello Alice"

    def test_resolve_list_values(self):
        """Test resolving config with list values."""
        config = {
            "recipients": ["{{admin}}", "{{user.email}}"]
        }
        data = {"admin": "admin@example.com", "user": {"email": "user@example.com"}}
        result = resolve_config(config, data)

        assert result["recipients"] == ["admin@example.com", "user@example.com"]

    def test_resolve_mixed_types(self):
        """Test resolving config with mixed value types."""
        config = {
            "name": "{{user.name}}",
            "age": 30,
            "active": True,
            "tags": ["tag1", "{{tag2}}"]
        }
        data = {"user": {"name": "Alice"}, "tag2": "dynamic"}
        result = resolve_config(config, data)

        assert result["name"] == "Alice"
        assert result["age"] == 30
        assert result["active"] is True
        assert result["tags"] == ["tag1", "dynamic"]

    def test_resolve_empty_config(self):
        """Test resolving empty config."""
        result = resolve_config({}, {"any": "data"})
        assert result == {}

    def test_resolve_preserves_non_string_list_items(self):
        """Test that non-string list items are preserved."""
        config = {
            "values": [1, 2, "{{name}}", True]
        }
        data = {"name": "test"}
        result = resolve_config(config, data)

        assert result["values"] == [1, 2, "test", True]
