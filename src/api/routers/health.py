from fastapi import APIRouter, HTTPException, Response, Depends
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from src.shared.logging_config import log
from src.api.application.service import WorkflowManagementService
from src.api.dependencies import get_service

router = APIRouter()


@router.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/health")
def health(service: WorkflowManagementService = Depends(get_service)):
    try:
        result = service.health_check()
        if result.get("status") != "healthy":
            raise HTTPException(status_code=503, detail=result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error("Health check failed", exc_info=True)
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "error": str(e)})


@router.get("/ready")
def ready(service: WorkflowManagementService = Depends(get_service)):
    try:
        with service.uow:
            service.uow.repo.cursor.execute("SELECT 1")
        return {"status": "ready"}
    except Exception:
        raise HTTPException(status_code=503, detail={"status": "not_ready"})
