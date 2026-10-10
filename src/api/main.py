import time
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4

from src.shared.logging_config import log
from src.shared.metrics import http_requests_total, http_request_duration_seconds

from src.api.auth import require_api_key, validate_auth_config
from src.api.exception_handlers import register_exception_handlers
from src.api.routers import health, connectors, connections, workflows, instances, triggers

@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_auth_config()   # refuse to start without a strong API key
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# Deny by default: every router needs the API key. The exceptions are /ready (inside the health router)
# and the provider webhooks in `triggers`, which verify their own signatures.
authenticated = [Depends(require_api_key)]
app.include_router(health.router)
app.include_router(connectors.router, dependencies=authenticated)
app.include_router(connections.router, dependencies=authenticated)
app.include_router(workflows.router, dependencies=authenticated)
app.include_router(instances.router, dependencies=authenticated)
app.include_router(triggers.router)


@app.middleware("http")
async def logging_and_metrics_middleware(request: Request, call_next):
    structlog.contextvars.clear_contextvars()
    request_id = str(uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    if request.url.path != "/metrics":
        http_requests_total.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code
        ).inc()

        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)

    structlog.contextvars.clear_contextvars()
    return response
