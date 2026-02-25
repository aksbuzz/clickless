from uuid import UUID
from fastapi import APIRouter, Depends

from src.api.application.service import WorkflowManagementService
from src.api.dependencies import get_service
from src.api.schemas import (
    CreateWorkflowPayload, CreateVersionPayload, WorkflowPayload,
    WorkflowCreatedOut, VersionCreatedOut, WorkflowStartedOut, WorkflowTriggeredOut,
)

router = APIRouter()


@router.post("/workflows", status_code=201, response_model=WorkflowCreatedOut)
def create_workflow(payload: CreateWorkflowPayload, service: WorkflowManagementService = Depends(get_service)):
    return service.create_workflow(payload.name, payload.definition)


@router.get("/workflows")
def list_workflows(service: WorkflowManagementService = Depends(get_service)):
    return service.list_workflows()


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: UUID, service: WorkflowManagementService = Depends(get_service)):
    return service.get_workflow(str(workflow_id))


@router.post("/workflows/{workflow_id}/versions", status_code=201, response_model=VersionCreatedOut)
def create_version(workflow_id: UUID, payload: CreateVersionPayload, service: WorkflowManagementService = Depends(get_service)):
    return service.create_version(str(workflow_id), payload.definition)


@router.post("/workflows/{definition_name}/run", response_model=WorkflowStartedOut)
def run_workflow(definition_name: str, payload: WorkflowPayload, service: WorkflowManagementService = Depends(get_service)):
    return service.start_workflow(definition_name, payload.data)


@router.post("/webhooks/{workflow_name}", response_model=WorkflowTriggeredOut)
def webhook_trigger(workflow_name: str, payload: WorkflowPayload = None, service: WorkflowManagementService = Depends(get_service)):
    data = payload.data if payload else {}
    return service.trigger_webhook(workflow_name, data)
