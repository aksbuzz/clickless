-- Migration 002: replace the outbox with the jobs table (docs/adr/0017 and 0018).
--
-- Stop the API and the old engine, worker and relay first. Messages still sitting in the outbox are
-- discarded; instead, every instance that had not finished gets a job for the step it was on, so it resumes.
-- A step that was in flight may run again (execution is at-least-once). A delay that was in progress starts
-- over, and an instance waiting for an event re-arms its wait.
-- Fresh databases get all of this from init.sql. Safe to run twice.

BEGIN;

CREATE TABLE IF NOT EXISTS jobs (
  id            BIGSERIAL PRIMARY KEY,
  instance_id   UUID NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
  step_name     VARCHAR(100) NOT NULL,
  kind          VARCHAR(20)  NOT NULL DEFAULT 'run_step' CHECK (kind IN ('run_step', 'wait_timeout')),
  status        VARCHAR(20)  NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'dead')),   -- finished jobs are deleted
  run_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
  attempts      INTEGER NOT NULL DEFAULT 0,
  claims        INTEGER NOT NULL DEFAULT 0,
  locked_by     TEXT,
  locked_until  TIMESTAMPTZ,
  last_error    TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_jobs_queued   ON jobs (run_at)       WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_jobs_running  ON jobs (locked_until) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS idx_jobs_instance ON jobs (instance_id);
CREATE INDEX IF NOT EXISTS idx_jobs_dead     ON jobs (id)           WHERE status = 'dead';

-- Only while the old outbox still exists, so running this again cannot add a second job to a running instance.
DO $$
BEGIN
  IF to_regclass('public.outbox') IS NOT NULL THEN
    INSERT INTO jobs (instance_id, step_name)
    SELECT i.id, COALESCE(i.current_step, v.definition->>'start_at')
    FROM workflow_instances i
    JOIN workflow_versions v ON v.id = i.workflow_version_id
    WHERE i.status IN ('pending', 'running')
      AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.instance_id = i.id);
    DROP TABLE outbox;
  END IF;
END $$;

-- Step executions are one row per attempt now, and the input snapshot is no longer stored.
ALTER TABLE workflow_step_executions DROP COLUMN IF EXISTS input_data;

COMMIT;
