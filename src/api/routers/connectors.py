from fastapi import APIRouter, Depends

from src.api.service import WorkflowManagementService
from src.api.dependencies import get_service

router = APIRouter()


@router.get("/connectors")
def list_connectors(service: WorkflowManagementService = Depends(get_service)):
    return service.list_connectors()
