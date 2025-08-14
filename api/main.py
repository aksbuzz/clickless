import structlog
import json
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from uuid import UUID, uuid4
from psycopg2.extras import RealDictCursor

from shared.loggin_config import setup_logging
from shared.db import get_db_connection

setup_logging()
log = structlog.get_logger()

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
  
  with get_db_connection() as conn:
    with conn.cursor() as cur:
      try:
        # get definition id
        cur.execute(
          "SELECT id FROM workflow_definitions " \
          "WHERE name = %s AND is_active = true; ",
          (definition_name,)
        )
        def_row = cur.fetchone()
        if not def_row:
          raise HTTPException(status_code=404, detail="Workflow definition not found")
        definition_id = def_row[0]

        # create workflow instance
        cur.execute(
          "INSERT INTO workflow_instances (definition_id, status, data, history) " \
          "VALUES (%s, 'PENDING', %s, '[]'::jsonb) " \
          "RETURNING id; ",
          (definition_id, json.dumps(payload.data),)
        )
        instance_id = cur.fetchone()[0]

        structlog.contextvars.bind_contextvars(instance_id=str(instance_id))
        log.info("Workflow instance created in DB, preparing outbox message")

        # outbox message to trigger engine
        outbox_payload = json.dumps({
          "type": "START_WORKFLOW",
          "instance_id": str(instance_id)
        })
        cur.execute(
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


@app.get("/instances/{instance_id}")
def get_instance_status(instance_id: UUID):
  with get_db_connection() as conn:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
      cur.execute("SELECT * FROM workflow_instances WHERE id = %s; ", (str(instance_id),))
      instance = cur.fetchone()
      if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
      return instance