from uuid import UUID
from fastapi import APIRouter, Depends

from src.api.service import WorkflowManagementService
from src.api.dependencies import get_service
from src.api.schemas import EventPayload, InstanceCancelledOut, EventSentOut

router = APIRouter()


@router.get("/instances")
def list_instances(
    status: str = None,
    workflow_id: UUID = None,
    limit: int = 50,
    offset: int = 0,
    service: WorkflowManagementService = Depends(get_service),
):
    return service.list_instances(
        status=status,
        workflow_id=str(workflow_id) if workflow_id else None,
        limit=limit,
        offset=offset,
    )


@router.get("/instances/{instance_id}")
def get_instance_status(instance_id: UUID, service: WorkflowManagementService = Depends(get_service)):
    return service.get_instance(str(instance_id))


@router.get("/instances/{instance_id}/steps")
def get_instance_steps(instance_id: UUID, service: WorkflowManagementService = Depends(get_service)):
    return service.get_instance_steps(str(instance_id))


@router.post("/instances/{instance_id}/cancel", response_model=InstanceCancelledOut)
def cancel_instance(instance_id: UUID, service: WorkflowManagementService = Depends(get_service)):
    return service.cancel_instance(str(instance_id))


@router.post("/instances/{instance_id}/events", response_model=EventSentOut)
def send_event(instance_id: UUID, payload: EventPayload, service: WorkflowManagementService = Depends(get_service)):
    return service.send_event(str(instance_id), payload.data)
