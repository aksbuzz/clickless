from fastapi import Request
from fastapi.responses import JSONResponse

from src.api.errors import (
    WorkflowNotFoundError, InstanceNotFoundError,
    ConnectionNotFoundError, InvalidStateError,
    DuplicateWorkflowError, DuplicateConnectionError, ValidationError,
)


def register_exception_handlers(app):
    @app.exception_handler(WorkflowNotFoundError)
    async def workflow_not_found(request: Request, exc: WorkflowNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Workflow not found"})

    @app.exception_handler(InstanceNotFoundError)
    async def instance_not_found(request: Request, exc: InstanceNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Instance not found"})

    @app.exception_handler(ConnectionNotFoundError)
    async def connection_not_found(request: Request, exc: ConnectionNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Connection not found"})

    @app.exception_handler(InvalidStateError)
    async def invalid_state(request: Request, exc: InvalidStateError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(DuplicateWorkflowError)
    async def duplicate_workflow(request: Request, exc: DuplicateWorkflowError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(DuplicateConnectionError)
    async def duplicate_connection(request: Request, exc: DuplicateConnectionError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, exc: ValidationError):
        return JSONResponse(status_code=400, content={"validation_errors": exc.errors})
