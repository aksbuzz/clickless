-- Finished runs are deleted after RETENTION_DAYS (ADR 0022). Finding them by age needs this index.
-- Safe to run more than once. On a very large table, run the statement on its own with CREATE INDEX CONCURRENTLY
-- to avoid blocking writes while it builds.
CREATE INDEX IF NOT EXISTS idx_instances_finished ON workflow_instances (updated_at)
  WHERE status IN ('completed', 'failed', 'cancelled');
