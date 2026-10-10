-- Migration: Add request_id for distributed tracing
-- Fresh databases already get these columns from infrastructure/postgres/init.sql.
-- Apply this file only to a database that was created before that change; it is idempotent.

-- Add request_id to workflow_instances
ALTER TABLE workflow_instances
  ADD COLUMN IF NOT EXISTS request_id VARCHAR(36);

CREATE INDEX IF NOT EXISTS idx_instances_request_id
  ON workflow_instances (request_id);

-- Add request_id to workflow_step_executions
ALTER TABLE workflow_step_executions
  ADD COLUMN IF NOT EXISTS request_id VARCHAR(36);

CREATE INDEX IF NOT EXISTS idx_step_exec_request_id
  ON workflow_step_executions (request_id);

-- Add request_id to outbox for debugging
ALTER TABLE outbox
  ADD COLUMN IF NOT EXISTS request_id VARCHAR(36);

CREATE INDEX IF NOT EXISTS idx_outbox_request_id
  ON outbox (request_id);
