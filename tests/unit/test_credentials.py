"""Encryption and redaction of connection credentials (src/shared/credentials.py)."""
import pytest
from cryptography.fernet import Fernet

from src.shared import credentials
from src.shared.credentials import (
    SecretDecryptionError,
    SecretsKeyError,
    decrypt,
    encrypt,
    is_encrypted,
    protect,
    redact,
    reveal,
    secret_fields,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "token": {"type": "string", "title": "Token", "writeOnly": True},
        "host": {"type": "string", "title": "Host"},
    },
    "required": ["token"],
}


def new_key():
    return Fernet.generate_key().decode()


@pytest.fixture
def key(monkeypatch):
    k = new_key()
    monkeypatch.setenv("SECRETS_KEY", k)
    return k


class TestEncryptDecrypt:
    def test_round_trip(self, key):
        assert decrypt(encrypt("ghp_abc123")) == "ghp_abc123"

    def test_the_stored_form_is_tagged_and_hides_the_value(self, key):
        stored = encrypt("ghp_abc123")
        assert is_encrypted(stored)
        assert stored.startswith("enc:v1:")
        assert "ghp_abc123" not in stored

    def test_the_same_value_encrypts_differently_each_time(self, key):
        assert encrypt("same") != encrypt("same")

    def test_plaintext_written_before_encryption_existed_still_reads(self, key):
        assert not is_encrypted("old-plain-token")
        assert decrypt("old-plain-token") == "old-plain-token"

    def test_a_wrong_key_fails_loudly(self, key, monkeypatch):
        stored = encrypt("secret")
        monkeypatch.setenv("SECRETS_KEY", new_key())
        with pytest.raises(SecretDecryptionError):
            decrypt(stored)

    def test_a_tampered_value_fails_loudly(self, key):
        stored = encrypt("secret")
        with pytest.raises(SecretDecryptionError):
            decrypt(stored[:-4] + "AAAA")

    def test_rotation_new_values_use_the_first_key_and_old_ones_still_read(self, key, monkeypatch):
        old_value = encrypt("written-with-old-key")
        new = new_key()
        monkeypatch.setenv("SECRETS_KEY", f"{new},{key}")
        assert decrypt(old_value) == "written-with-old-key"
        fresh = encrypt("written-with-new-key")
        monkeypatch.setenv("SECRETS_KEY", new)   # the old key can be dropped once everything is re-encrypted
        assert decrypt(fresh) == "written-with-new-key"
        with pytest.raises(SecretDecryptionError):
            decrypt(old_value)


class TestKeyHandling:
    def test_encrypting_without_a_key_is_refused(self, monkeypatch):
        monkeypatch.delenv("SECRETS_KEY", raising=False)
        with pytest.raises(SecretsKeyError, match="SECRETS_KEY"):
            encrypt("secret")

    def test_decrypting_an_encrypted_value_without_a_key_is_refused(self, key, monkeypatch):
        stored = encrypt("secret")
        monkeypatch.delenv("SECRETS_KEY", raising=False)
        with pytest.raises(SecretsKeyError, match="SECRETS_KEY"):
            decrypt(stored)

    def test_plaintext_needs_no_key_to_read(self, monkeypatch):
        monkeypatch.delenv("SECRETS_KEY", raising=False)
        assert decrypt("plain") == "plain"

    def test_a_malformed_key_is_reported_with_how_to_make_one(self, monkeypatch):
        monkeypatch.setenv("SECRETS_KEY", "not-a-fernet-key")
        with pytest.raises(SecretsKeyError, match="Fernet"):
            encrypt("secret")

    def test_check_configured_fails_fast_for_start_up(self, monkeypatch):
        monkeypatch.delenv("SECRETS_KEY", raising=False)
        with pytest.raises(SecretsKeyError):
            credentials.check_configured()
        monkeypatch.setenv("SECRETS_KEY", new_key())
        credentials.check_configured()


class TestSchemaAwareHelpers:
    def test_secret_fields_are_the_write_only_properties(self):
        assert secret_fields(SCHEMA) == {"token"}

    def test_a_schema_without_properties_has_no_secrets(self):
        assert secret_fields({}) == set()

    def test_protect_encrypts_only_the_secret_fields(self, key):
        stored = protect({"token": "ghp_x", "host": "github.com"}, SCHEMA)
        assert is_encrypted(stored["token"])
        assert stored["host"] == "github.com"

    def test_protect_leaves_an_already_encrypted_value_alone(self, key):
        once = protect({"token": "ghp_x"}, SCHEMA)
        twice = protect(once, SCHEMA)
        assert twice["token"] == once["token"]

    def test_protect_does_not_modify_its_input(self, key):
        original = {"token": "ghp_x"}
        protect(original, SCHEMA)
        assert original == {"token": "ghp_x"}

    def test_reveal_decrypts_every_encrypted_value(self, key):
        stored = protect({"token": "ghp_x", "host": "github.com"}, SCHEMA)
        assert reveal(stored) == {"token": "ghp_x", "host": "github.com"}

    def test_reveal_passes_legacy_plaintext_through(self, key):
        assert reveal({"token": "legacy"}) == {"token": "legacy"}

    def test_redact_removes_secret_values_and_says_which_are_set(self, key):
        stored = protect({"token": "ghp_x", "host": "github.com"}, SCHEMA)
        public, secrets_set = redact(stored, SCHEMA)
        assert public == {"host": "github.com"}
        assert secrets_set == ["token"]
        assert "ghp_x" not in str(public)

    def test_redact_does_not_list_an_empty_secret_as_set(self):
        public, secrets_set = redact({"token": ""}, SCHEMA)
        assert public == {}
        assert secrets_set == []

    def test_redact_works_without_a_key(self, monkeypatch):
        monkeypatch.delenv("SECRETS_KEY", raising=False)
        public, secrets_set = redact({"token": "enc:v1:abc", "host": "h"}, SCHEMA)
        assert public == {"host": "h"} and secrets_set == ["token"]


MULTI_SCHEMA = {
    "type": "object",
    "properties": {
        "api_key": {"type": "string", "title": "API Key", "writeOnly": True},
        "api_token": {"type": "string", "title": "API Token", "writeOnly": True},
        "host": {"type": "string", "title": "Host"},
        "port": {"type": "integer", "title": "Port"},
    },
    "required": ["api_key", "api_token"],
}


class TestValidateConfig:
    def test_a_complete_config_has_no_problems(self):
        assert credentials.validate_config({"api_key": "k", "api_token": "t"}, MULTI_SCHEMA) == []

    def test_missing_and_blank_required_fields_are_named_by_title(self):
        problems = credentials.validate_config({"api_key": "  "}, MULTI_SCHEMA)
        assert problems == ["API Key is required", "API Token is required"]

    def test_unknown_fields_are_rejected_so_nothing_unprotected_is_stored(self):
        problems = credentials.validate_config({"api_key": "k", "api_token": "t", "password": "x"}, MULTI_SCHEMA)
        assert problems == ["Unknown field 'password'"]

    def test_a_string_field_must_hold_a_string(self):
        problems = credentials.validate_config({"api_key": 123, "api_token": "t"}, MULTI_SCHEMA)
        assert problems == ["API Key must be text"]

    def test_other_types_are_not_policed(self):
        assert credentials.validate_config({"api_key": "k", "api_token": "t", "port": 5432}, MULTI_SCHEMA) == []

    def test_a_secret_that_is_already_stored_satisfies_required(self):
        problems = credentials.validate_config({"host": "h"}, MULTI_SCHEMA, keep={"api_key", "api_token"})
        assert problems == []

    def test_the_config_must_be_an_object(self):
        assert credentials.validate_config(["x"], MULTI_SCHEMA) == ["config must be an object"]


class TestMergeUpdate:
    stored = {"api_key": "enc:v1:KEY", "api_token": "enc:v1:TOKEN", "host": "old.example"}

    def test_a_secret_left_out_keeps_its_stored_value(self):
        merged = credentials.merge_update({"host": "new.example"}, self.stored, MULTI_SCHEMA)
        assert merged == {"api_key": "enc:v1:KEY", "api_token": "enc:v1:TOKEN", "host": "new.example"}

    def test_a_blank_secret_keeps_its_stored_value(self):
        merged = credentials.merge_update({"api_key": "", "api_token": None}, self.stored, MULTI_SCHEMA)
        assert merged["api_key"] == "enc:v1:KEY" and merged["api_token"] == "enc:v1:TOKEN"

    def test_a_new_secret_replaces_the_stored_one(self):
        merged = credentials.merge_update({"api_key": "fresh"}, self.stored, MULTI_SCHEMA)
        assert merged["api_key"] == "fresh" and merged["api_token"] == "enc:v1:TOKEN"

    def test_non_secret_fields_come_only_from_the_new_config(self):
        merged = credentials.merge_update({"api_key": "k"}, self.stored, MULTI_SCHEMA)
        assert "host" not in merged

    def test_with_nothing_stored_blank_secrets_are_dropped(self):
        merged = credentials.merge_update({"api_key": "k", "api_token": ""}, {}, MULTI_SCHEMA)
        assert merged == {"api_key": "k"}

    def test_stored_secrets_are_the_ones_that_hold_a_value(self):
        assert credentials.stored_secrets({"api_key": "enc:v1:KEY", "api_token": ""}, MULTI_SCHEMA) == {"api_key"}
