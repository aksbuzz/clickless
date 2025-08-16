import structlog
import json
import psycopg2
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from uuid import UUID, uuid4
from psycopg2.extras import RealDictCursor

from src.shared.logging_config import log
from src.shared.db import get_db_connection

app = FastAPI()

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
  structlog.contextvars.clear_contextvars()
  
  request_id = str(uuid4())
  structlog.contextvars.bind_contextvars(request_id=request_id)
  
  response = await call_next(request)

  structlog.contextvars.clear_contextvars()
  return response


class WorkflowPayload(BaseModel):
  data: dict


@app.post("/workflows/{definition_name}/run")
def run_workflow(definition_name: str, payload: WorkflowPayload):
  log.info("Received request to start workflow", definition=definition_name)

  conn = psycopg2.connect(get_db_connection(), cursor_factory=RealDictCursor)
  cursor = conn.cursor()
  try:
    # get definition id
    cursor.execute(
      "SELECT id FROM workflow_definitions " \
      "WHERE name = %s AND is_active = true; ",
      (definition_name,)
    )
    def_row = cursor.fetchone()
    if not def_row:
      raise HTTPException(status_code=404, detail="Workflow definition not found")
    definition_id = def_row["id"]

    # create workflow instance
    cursor.execute(
      "INSERT INTO workflow_instances (definition_id, status, data, history) " \
      "VALUES (%s, 'PENDING', %s, '[]'::jsonb) " \
      "RETURNING id; ",
      (definition_id, json.dumps(payload.data),)
    )
    instance_id = cursor.fetchone()["id"]

    structlog.contextvars.bind_contextvars(instance_id=str(instance_id))
    log.info("Workflow instance created in DB, preparing outbox message")

    # outbox message to trigger engine
    outbox_payload = json.dumps({
      "type": "START_WORKFLOW",
      "instance_id": str(instance_id)
    })
    cursor.execute(
      "INSERT INTO outbox (destination, payload) " \
      "VALUES (%s, %s); ",
      ('orchestration_queue', outbox_payload)
    )

    conn.commit()
    
    log.info("Workflow started successfully")
    return {"message": "Workflow started", "instance_id": instance_id}
  
  except Exception as e:
    conn.rollback()
    log.error("Failed to start workflow", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Failed to start workflow: {e}")
  finally:
    if cursor:
      cursor.close()
    if conn:
      conn.close()


@app.get("/instances/{instance_id}")
def get_instance_status(instance_id: UUID):
  conn = psycopg2.connect(get_db_connection(), cursor_factory=RealDictCursor)
  cursor = conn.cursor()
  try:
    cursor.execute("SELECT * FROM workflow_instances WHERE id = %s; ", (str(instance_id),))
    instance = cursor.fetchone()
  finally:
    if cursor:
      cursor.close()
    if conn:
      conn.close()
  
  if not instance:
    raise HTTPException(status_code=404, detail="Instance not found")
  return instance