import time

from src.shared.logging_config import log

from src.worker.domain.ports import ActionHandlerPort, ActionResult


class FetchInvoiceHandler(ActionHandlerPort):
  def execute(self, instance_id, data, **kwargs):
    log.info(f"Fetching invoice...", instance_id=instance_id)
    
    time.sleep(2) # Simulate n/w call
    
    amount = data.get('invoice_details', {}).get('amount', 0)
    data['invoice_details'] = {'amount': amount or 1200, 'customer': 'Big Corp'}
    
    return ActionResult("succeeded", data)

class ValidateInvoiceHandler(ActionHandlerPort):
  def execute(self, instance_id, data, **kwargs):
    log.info(f"Validating invoice...", instance_id=instance_id)
    amount = data.get('invoice_details', {}).get('amount', 0)
    
    # Simulate business error
    if amount > 1000:
      data['is_valid'] = True
      return ActionResult("succeeded", data)
    else:
      data['is_valid'] = False
      data['error'] = "Invoice amount is too low for this test."
      return ActionResult("failed", data)

class GenerateReportHandler(ActionHandlerPort):
  def execute(self, instance_id, data, **kwargs):
    log.info(f"Generating PDF report...", instance_id=instance_id)
    report_content = f"Invoice Report for {data['invoice_details']['customer']}\nAmount: ${data['invoice_details']['amount']}"
    
    data['report_content'] = report_content
    return ActionResult("succeeded", data)

class ArchiveReportHandler(ActionHandlerPort):
  def execute(self, instance_id, data, **kwargs):
    task_context = kwargs["task_context"]
    current_attempt = task_context.request.retries + 1

    # Simulate action failing due to transient errors
    if task_context.request.retries < 2:
      log.error("Simulating archive failure", attempt=current_attempt, instance_id=instance_id)
      raise ConnectionError("Archive S3 simulation failed")
    
    log.info("Archiving report to S3...",attempt=current_attempt, instance_id=instance_id)  
    object_name = f"{instance_id}/report.txt"

    time.sleep(2) # Simulate storing to S3
    data['report_archive_path'] = f"s3://bucket/{object_name}"
    
    if 'report_content' in data:
      del data['report_content']

    return ActionResult("succeeded", data)

class InitialStepHandler(ActionHandlerPort):
  def execute(self, instance_id, data, **kwargs):
    log.info(f"Executing the initial step.", instance_id=instance_id)
    data['initial_step_done'] = True
    return ActionResult("succeeded", data)

class FinalStepHandler(ActionHandlerPort):
  def execute(self, instance_id, data, **kwargs):
    log.info(f"Executing the final step after the delay.", instance_id=instance_id)
    data['final_step_done'] = True
    return ActionResult("succeeded", data)