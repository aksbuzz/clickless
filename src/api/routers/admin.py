from fastapi import APIRouter, Depends

from src.api.service import WorkflowManagementService
from src.api.dependencies import get_service
from src.api.schemas import RecoveryOut

router = APIRouter()


@router.post("/admin/recover", response_model=RecoveryOut)
def recover_stuck_instances(stale_seconds: int = 60, service: WorkflowManagementService = Depends(get_service)):
    recovered = service.recover_stuck_instances(stale_seconds)
    return {"message": f"Recovered {len(recovered)} instance(s)", "recovered": recovered}
