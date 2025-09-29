CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE workflow_definitions (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) UNIQUE NOT NULL,
  definition JSONB NOT NULL,
  is_active BOOLEAN DEFAULT true
);


-- store state of each running workflow
CREATE TABLE workflow_instances (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  definition_id INTEGER REFERENCES workflow_definitions(id),
  status VARCHAR(50) NOT NULL,
  current_step VARCHAR(100),
  current_step_attempts INTEGER DEFAULT 0,
  data JSONB,
  history JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


CREATE TABLE outbox (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  destination VARCHAR(255) NOT NULL,
  payload JSONB NOT NULL,
  publish_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  processed_at TIMESTAMP WITH TIME ZONE NULL
);
CREATE INDEX idx_outbox_unprocessed ON outbox (processed_at) WHERE processed_at IS NULL;


CREATE TABLE action_definitions (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) UNIQUE NOT NULL,
  description TEXT,
  
  handler_type VARCHAR(100) NOT NULL, -- e.g., 'http_request', 'python_function'

  config JSONB NOT NULL,

  version INT NOT NULL DEFAULT 1,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (name, version)
);


-- SEED
INSERT INTO workflow_definitions (name, definition)
VALUES ('invoice_approval', '{
  "description": "A simple invoice approval flow.",
  "start_at": "fetch_invoice",
  "steps": {
    "fetch_invoice": { "next": "validate_invoice" },
    "validate_invoice": { "next": "generate_report" },
    "generate_report": { "next": "archive_report" },
    "archive_report": { 
      "next": "end",
      "retry": {
        "max_attempts": 3,
        "delay_seconds": 5
      }
    }
  }
}');