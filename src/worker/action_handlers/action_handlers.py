import time
import httpx

from src.shared.logging_config import log

from src.worker.domain.models import ActionStatus, ActionResult
from src.worker.registry import action

DEFAULT_TIMEOUT = 30


@action("fetch_invoice")
class FetchInvoiceHandler:
  def execute(self, instance_id, data, **kwargs):
    log.info(f"Fetching invoice...", instance_id=instance_id)
    
    time.sleep(2) # Simulate n/w call
    
    amount = data.get('invoice_details', {}).get('amount', 0)
    data['invoice_details'] = {'amount': amount or 1200, 'customer': 'Big Corp'}
    
    return ActionResult(ActionStatus.SUCCESS, data)

@action("validate_invoice")
class ValidateInvoiceHandler:
  def execute(self, instance_id, data, **kwargs):
    log.info(f"Validating invoice...", instance_id=instance_id)
    amount = data.get('invoice_details', {}).get('amount', 0)
    
    # Simulate business error
    if amount > 1000:
      data['is_valid'] = True
      return ActionResult(ActionStatus.SUCCESS, data)
    else:
      data['is_valid'] = False
      data['error'] = "Invoice amount is too low for this test."
      return ActionResult(ActionStatus.FAILURE, data)

@action("generate_report")
class GenerateReportHandler:
  def execute(self, instance_id, data, **kwargs):
    log.info(f"Generating PDF report...", instance_id=instance_id)
    report_content = f"Invoice Report for {data['invoice_details']['customer']}\nAmount: ${data['invoice_details']['amount']}"
    
    data['report_content'] = report_content
    return ActionResult(ActionStatus.SUCCESS, data)

@action("archive_report")
class ArchiveReportHandler:
  def execute(self, instance_id, data, **kwargs):
    log.info("Archiving report to S3...", instance_id=instance_id)

    time.sleep(2)  # Simulate storing to S3
    object_name = f"{instance_id}/report.txt"
    data['report_archive_path'] = f"s3://bucket/{object_name}"

    if 'report_content' in data:
      del data['report_content']

    return ActionResult(ActionStatus.SUCCESS, data)

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

    log.info("Sending HTTP request", instance_id=instance_id, method=method, url=url)
    try:
      response = httpx.request(method, url, headers=headers, json=body, timeout=timeout)
      data["http_response"] = {
        "status_code": response.status_code,
        "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
      }
      log.info("HTTP response received", instance_id=instance_id, status_code=response.status_code)
      if response.is_success:
        return ActionResult(ActionStatus.SUCCESS, data)
      else:
        return ActionResult(ActionStatus.FAILURE, data, error_message=f"HTTP {response.status_code}")
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

    log.info("Sending webhook", instance_id=instance_id, url=url)
    try:
      response = httpx.post(url, json=data, headers=headers, timeout=timeout)
      data["webhook_response"] = {"status_code": response.status_code}
      log.info("Webhook delivered", instance_id=instance_id, status_code=response.status_code)
      if response.is_success:
        return ActionResult(ActionStatus.SUCCESS, data)
      else:
        return ActionResult(ActionStatus.FAILURE, data, error_message=f"Webhook returned HTTP {response.status_code}")
    except httpx.TimeoutException:
      return ActionResult(ActionStatus.FAILURE, data, error_message=f"Webhook timed out after {timeout}s")
    except httpx.RequestError as e:
      return ActionResult(ActionStatus.FAILURE, data, error_message=f"Webhook error: {e}")