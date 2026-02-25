from uuid import UUID
from fastapi import APIRouter, Depends

from src.api.application.service import WorkflowManagementService
from src.api.dependencies import get_service
from src.api.schemas import (
    CreateConnectionPayload, UpdateConnectionPayload,
    ConnectionCreatedOut, MessageOut,
)

router = APIRouter()


@router.post("/connections", status_code=201, response_model=ConnectionCreatedOut)
def create_connection(payload: CreateConnectionPayload, service: WorkflowManagementService = Depends(get_service)):
    return service.create_connection(payload.connector_id, payload.name, payload.config)


@router.get("/connections")
def list_connections(connector_id: str = None, service: WorkflowManagementService = Depends(get_service)):
    return service.list_connections(connector_id)


@router.get("/connections/{connection_id}")
def get_connection(connection_id: UUID, service: WorkflowManagementService = Depends(get_service)):
    return service.get_connection(str(connection_id))


@router.put("/connections/{connection_id}")
def update_connection(connection_id: UUID, payload: UpdateConnectionPayload, service: WorkflowManagementService = Depends(get_service)):
    return service.update_connection(str(connection_id), payload.name, payload.config)


@router.delete("/connections/{connection_id}", response_model=MessageOut)
def delete_connection(connection_id: UUID, service: WorkflowManagementService = Depends(get_service)):
    return service.delete_connection(str(connection_id))
