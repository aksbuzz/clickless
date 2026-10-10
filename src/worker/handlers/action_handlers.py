import json
import time
import httpx

from src.shared.logging_config import log
from src.shared.net_guard import OutboundBlocked, ResponseTooLarge, check_url, read_limited

from src.worker.models import ActionStatus, ActionResult
from src.worker.registry import action

DEFAULT_TIMEOUT = 30


@action("initial_step")
class InitialStepHandler:
  def execute(self, instance_id, data, **kwargs):
    log.info(f"Executing the initial step.", instance_id=instance_id)
    data['initial_step_done'] = True
    return ActionResult(ActionStatus.SUCCESS, data)

@action("final_step")
class FinalStepHandler:
  def execute(self, instance_id, data, **kwargs):
    log.info(f"Executing the final step after the delay.", instance_id=instance_id)
    data['final_step_done'] = True
    return ActionResult(ActionStatus.SUCCESS, data)


@action("log")
class LogHandler:
  def execute(self, instance_id, data, config=None, **kwargs):
    config = config or {}
    message = config.get("message", "Log step executed")
    log.info(message, instance_id=instance_id, workflow_data=data)
    return ActionResult(ActionStatus.SUCCESS, data)


@action("transform_data")
class TransformDataHandler:
  def execute(self, instance_id, data, config=None, **kwargs):
    config = config or {}
    # Set fields
    for key, value in config.get("set", {}).items():
      data[key] = value
    # Remove fields
    for key in config.get("remove", []):
      data.pop(key, None)
    log.info("Data transformed", instance_id=instance_id)
    return ActionResult(ActionStatus.SUCCESS, data)


def _decode_body(content: bytes, content_type: str):
  text = content.decode("utf-8", errors="replace")
  if content_type.startswith("application/json"):
    try:
      return json.loads(text)
    except ValueError:
      return text
  return text


@action("http_request")
class HttpRequestHandler:
  def execute(self, instance_id, data, config=None, **kwargs):
    config = config or {}
    url = config.get("url", "")
    method = config.get("method", "GET").upper()
    headers = config.get("headers", {})
    body = config.get("body")
    timeout = config.get("timeout_seconds", DEFAULT_TIMEOUT)

    if not url:
      return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'url' in config")
    try:
      check_url(url)
    except OutboundBlocked as e:
      return ActionResult(ActionStatus.FAILURE, data, error_message=f"Blocked outbound request: {e}")

    log.info("Sending HTTP request", instance_id=instance_id, method=method, url=url)
    try:
      with httpx.stream(method, url, headers=headers, json=body, timeout=timeout) as response:
        content = read_limited(response)
        status_code = response.status_code
        content_type = response.headers.get("content-type", "")
        is_success = response.is_success
      data["http_response"] = {"status_code": status_code, "body": _decode_body(content, content_type)}
      log.info("HTTP response received", instance_id=instance_id, status_code=status_code)
      if is_success:
        return ActionResult(ActionStatus.SUCCESS, data)
      else:
        return ActionResult(ActionStatus.FAILURE, data, error_message=f"HTTP {status_code}")
    except ResponseTooLarge as e:
      return ActionResult(ActionStatus.FAILURE, data, error_message=f"Response too large: {e}")
    except httpx.TimeoutException:
      return ActionResult(ActionStatus.FAILURE, data, error_message=f"Request timed out after {timeout}s")
    except httpx.RequestError as e:
      return ActionResult(ActionStatus.FAILURE, data, error_message=f"Request error: {e}")


@action("send_webhook")
class SendWebhookHandler:
  def execute(self, instance_id, data, config=None, **kwargs):
    config = config or {}
    url = config.get("url", "")
    headers = config.get("headers", {})
    timeout = config.get("timeout_seconds", DEFAULT_TIMEOUT)

    if not url:
      return ActionResult(ActionStatus.FAILURE, data, error_message="Missing 'url' in config")
    try:
      check_url(url)
    except OutboundBlocked as e:
      return ActionResult(ActionStatus.FAILURE, data, error_message=f"Blocked outbound request: {e}")

    log.info("Sending webhook", instance_id=instance_id, url=url)
    try:
      with httpx.stream("POST", url, json=data, headers=headers, timeout=timeout) as response:
        status_code, is_success = response.status_code, response.is_success
      data["webhook_response"] = {"status_code": status_code}
      log.info("Webhook delivered", instance_id=instance_id, status_code=status_code)
      if is_success:
        return ActionResult(ActionStatus.SUCCESS, data)
      else:
        return ActionResult(ActionStatus.FAILURE, data, error_message=f"Webhook returned HTTP {status_code}")
    except httpx.TimeoutException:
      return ActionResult(ActionStatus.FAILURE, data, error_message=f"Webhook timed out after {timeout}s")
    except httpx.RequestError as e:
      return ActionResult(ActionStatus.FAILURE, data, error_message=f"Webhook error: {e}")
