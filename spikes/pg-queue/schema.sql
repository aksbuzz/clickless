-- Spike schema: applied on top of infrastructure/postgres/init.sql (the existing tables are reused).
-- One table replaces: outbox, relay, RabbitMQ queues and DLQs, Celery acks, the Redis lock and the sweeper.

CREATE TABLE IF NOT EXISTS jobs (
  id            BIGSERIAL PRIMARY KEY,
  instance_id   UUID NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
  step_name     VARCHAR(100) NOT NULL,
  kind          VARCHAR(20)  NOT NULL DEFAULT 'run_step' CHECK (kind IN ('run_step', 'wait_timeout')),
  status        VARCHAR(20)  NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'done', 'dead', 'cancelled')),
  run_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),   -- delay, retry backoff and wait timeouts all use this
  attempts      INTEGER NOT NULL DEFAULT 0,            -- handler-reported failures (compared with the step retry policy)
  claims        INTEGER NOT NULL DEFAULT 0,            -- times a worker took the job (guards against a step that kills workers)
  locked_by     TEXT,
  locked_until  TIMESTAMPTZ,                           -- the lease; an expired lease makes the job claimable again
  last_error    TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_queued   ON jobs (run_at)       WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS jobs_running  ON jobs (locked_until) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS jobs_instance ON jobs (instance_id);
