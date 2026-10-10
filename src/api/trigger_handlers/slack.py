import hashlib
import hmac
import json
import time
from typing import Any, Dict, List

from src.shared.logging_config import log
from src.shared.triggers.models import TriggerEvent, TriggerValidationResult
from src.shared.triggers.ports import TriggerHandlerPort


class SlackTriggerHandler(TriggerHandlerPort):

    def validate_webhook(self, headers: Dict[str, str], body: bytes, config: Dict[str, Any]) -> TriggerValidationResult:
        signing_secret = config.get("signing_secret")
        if not signing_secret:
            # Fail closed, including for the url_verification handshake.
            log.error("Slack webhook rejected: no signing secret is configured (set SLACK_SIGNING_SECRET)")
            return TriggerValidationResult(is_valid=False, error_message="Signing secret is not configured")

        timestamp = headers.get("x-slack-request-timestamp", "")
        slack_signature = headers.get("x-slack-signature", "")

        if not timestamp or not slack_signature:
            return TriggerValidationResult(is_valid=False, error_message="Missing Slack signature headers")

        # Reject requests older than 5 minutes (replay protection)
        try:
            if abs(time.time() - float(timestamp)) > 300:
                return TriggerValidationResult(is_valid=False, error_message="Request timestamp too old")
        except ValueError:
            return TriggerValidationResult(is_valid=False, error_message="Invalid timestamp")

        sig_basestring = b"v0:" + timestamp.encode("utf-8") + b":" + body
        expected_sig = "v0=" + hmac.new(
            signing_secret.encode("utf-8"),
            sig_basestring,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_sig.encode("utf-8"), slack_signature.encode("utf-8")):
            return TriggerValidationResult(is_valid=False, error_message="Invalid Slack signature")

        # Only a verified request may complete Slack's url_verification handshake.
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("type") == "url_verification":
            return TriggerValidationResult(is_valid=True, challenge_response=payload.get("challenge", ""))

        return TriggerValidationResult(is_valid=True)

    def parse_events(self, headers: Dict[str, str], body: bytes) -> List[TriggerEvent]:
        payload = json.loads(body)

        if payload.get("type") == "url_verification":
            return []

        if payload.get("type") != "event_callback":
            log.info("Ignoring non-event_callback Slack payload", type=payload.get("type"))
            return []

        event = payload.get("event", {})
        event_type = event.get("type")

        if event_type != "message":
            log.info("Ignoring unmapped Slack event", event_type=event_type)
            return []

        # Ignore bot messages to prevent loops
        if event.get("subtype") == "bot_message" or event.get("bot_id"):
            return []

        data = {
            "message": {
                "text": event.get("text", ""),
                "user": event.get("user", ""),
                "channel": event.get("channel", ""),
                "ts": event.get("ts", ""),
                "thread_ts": event.get("thread_ts"),
            },
            "team_id": payload.get("team_id", ""),
        }

        return [TriggerEvent(
            connector_id="slack",
            trigger_id="slack_message_received",
            source_event_type=event_type,
            data=data,
            metadata={
                "channel": event.get("channel", ""),
                "team_id": payload.get("team_id", ""),
            },
        )]

    def matches_workflow_config(self, event: TriggerEvent, workflow_trigger_config: Dict[str, Any]) -> bool:
        config_channel = workflow_trigger_config.get("channel")
        if config_channel:
            if config_channel != event.metadata.get("channel", ""):
                return False

        config_team = workflow_trigger_config.get("team_id")
        if config_team:
            if config_team != event.metadata.get("team_id", ""):
                return False

        return True
