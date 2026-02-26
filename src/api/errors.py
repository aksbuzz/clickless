class WorkflowError(Exception):
  pass

class WorkflowNotFoundError(WorkflowError):
  pass

class InstanceNotFoundError(WorkflowError):
  pass

class InvalidStateError(WorkflowError):
  pass

class DuplicateWorkflowError(WorkflowError):
  pass

class ConnectionNotFoundError(WorkflowError):
  pass

class DuplicateConnectionError(WorkflowError):
  pass

class ValidationError(WorkflowError):
  def __init__(self, errors: list):
    self.errors = errors
    super().__init__(f"Validation errors: {errors}")
