from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


# --- Request Models ---

class WorkflowPayload(BaseModel):
    data: dict


class CreateWorkflowPayload(BaseModel):
    name: str
    definition: dict


class CreateVersionPayload(BaseModel):
    definition: dict


class EventPayload(BaseModel):
    data: dict = {}


class CreateConnectionPayload(BaseModel):
    connector_id: str
    name: str
    config: dict


class UpdateConnectionPayload(BaseModel):
    name: str
    config: dict


# --- Response Models ---

class WorkflowCreatedOut(BaseModel):
    workflow_id: str
    version_id: str
    version: int


class VersionCreatedOut(BaseModel):
    version_id: str
    version: int


class WorkflowStartedOut(BaseModel):
    message: str
    instance_id: str


class WorkflowTriggeredOut(BaseModel):
    message: str
    instance_id: str


class InstanceCancelledOut(BaseModel):
    message: str
    instance_id: str


class EventSentOut(BaseModel):
    message: str
    instance_id: str
    step: str


class ConnectionCreatedOut(BaseModel):
    connection_id: str


class MessageOut(BaseModel):
    message: str


class RecoveryOut(BaseModel):
    message: str
    recovered: list


class TriggerResultOut(BaseModel):
    message: str
    triggered: list
