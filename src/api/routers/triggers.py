import os

from fastapi import APIRouter, HTTPException, Request, Response, Depends

from src.shared.logging_config import log
from src.shared.triggers.registry import TriggerHandlerRegistry
from src.api.application.service import WorkflowManagementService
from src.api.dependencies import get_service, get_trigger_registry
from src.api.schemas import TriggerResultOut

router = APIRouter()


def _get_connector_config(connector_id: str) -> dict:
    if connector_id == "github":
        return {"webhook_secret": os.getenv("GITHUB_WEBHOOK_SECRET", "")}
    elif connector_id == "slack":
        return {"signing_secret": os.getenv("SLACK_SIGNING_SECRET", "")}
    return {}


@router.head("/triggers/{connector_id}/webhook")
def trigger_webhook_head(
    connector_id: str,
    trigger_registry: TriggerHandlerRegistry = Depends(get_trigger_registry),
):
    handler = trigger_registry.get_handler(connector_id)
    if not handler:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {connector_id}")
    return Response(status_code=200)


@router.post("/triggers/{connector_id}/webhook", response_model=TriggerResultOut)
async def trigger_webhook_external(
    connector_id: str,
    request: Request,
    service: WorkflowManagementService = Depends(get_service),
    trigger_registry: TriggerHandlerRegistry = Depends(get_trigger_registry),
):
    handler = trigger_registry.get_handler(connector_id)
    if not handler:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {connector_id}")

    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    connector_config = _get_connector_config(connector_id)

    validation = handler.validate_webhook(headers, body, connector_config)
    if not validation.is_valid:
        log.warning("Webhook validation failed", connector=connector_id, error=validation.error_message)
        raise HTTPException(status_code=401, detail=validation.error_message)

    if validation.challenge_response is not None:
        return {"challenge": validation.challenge_response}

    try:
        events = handler.parse_events(headers, body)
    except Exception as e:
        log.error("Failed to parse webhook payload", connector=connector_id, error=str(e))
        raise HTTPException(status_code=400, detail="Failed to parse webhook payload")

    if not events:
        return {"message": "Acknowledged, no matching trigger events", "triggered": []}

    all_started = []
    for event in events:
        started = service.process_external_trigger(event, handler)
        all_started.extend(started)

    return {
        "message": f"Processed {len(events)} event(s), started {len(all_started)} workflow(s)",
        "triggered": all_started,
    }
