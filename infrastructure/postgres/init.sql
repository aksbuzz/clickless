CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE workflows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) UNIQUE NOT NULL,
  -- current_version INTEGER, 
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


CREATE TABLE workflow_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id UUID NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  definition JSONB NOT NULL,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
  UNIQUE (workflow_id, version)
);


CREATE TABLE workflow_instances (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_version_id UUID NOT NULL,
  status VARCHAR(50) NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
  current_step VARCHAR(100),
  current_step_attempts INTEGER DEFAULT 0,
  data JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  FOREIGN KEY (workflow_version_id) REFERENCES workflow_versions(id)
);
CREATE INDEX idx_instances_status ON workflow_instances (status);


CREATE TABLE workflow_step_executions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  instance_id UUID NOT NULL,
  step_name VARCHAR(100) NOT NULL,
  status VARCHAR(50) NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  attempts INTEGER DEFAULT 1,
  started_at TIMESTAMP WITH TIME ZONE NOT NULL,
  completed_at TIMESTAMP WITH TIME ZONE,
  input_data JSONB,
  output_data JSONB,
  error_details TEXT,
  
  FOREIGN KEY (instance_id) REFERENCES workflow_instances(id) ON DELETE CASCADE
);
CREATE INDEX idx_step_exec_instance ON workflow_step_executions (instance_id);
CREATE INDEX idx_step_exec_status ON workflow_step_executions (status);


CREATE TABLE outbox (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  destination VARCHAR(255) NOT NULL,
  payload JSONB NOT NULL,
  publish_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  processed_at TIMESTAMP WITH TIME ZONE NULL
);
CREATE INDEX idx_outbox_unprocessed ON outbox (processed_at) WHERE processed_at IS NULL;

CREATE INDEX idx_versions_trigger ON workflow_versions (
  (definition->'trigger'->>'connector_id'),
  (definition->'trigger'->>'trigger_id')
) WHERE is_active = true;

CREATE TABLE connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  connector_id VARCHAR(100) NOT NULL,
  name VARCHAR(255) NOT NULL,
  config JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE (connector_id, name)
);
CREATE INDEX idx_connections_connector ON connections (connector_id);


-- Auto-update trigger for updated_at columns
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_workflows_updated_at
  BEFORE UPDATE ON workflows
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_workflow_instances_updated_at
  BEFORE UPDATE ON workflow_instances
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_connections_updated_at
  BEFORE UPDATE ON connections
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- SEED
DO $$
DECLARE
  wf_id UUID;
BEGIN
  INSERT INTO workflows (name) VALUES ('order_priority_workflow') RETURNING id INTO wf_id;

  INSERT INTO workflow_versions (workflow_id, version, definition) VALUES (wf_id, 1, '{
    "description": "Classify order priority by quantity and set shipping days.",
    "trigger": {
      "connector_id": "http",
      "trigger_id": "http_request_received",
      "config": {}
    },
    "start_at": "compute_priority",
    "steps": {
      "compute_priority": {
        "type": "action",
        "connector_id": "python",
        "action_id": "python_execute",
        "config": {
          "code": "qty = data.get(''order'', {}).get(''quantity'', 0)\ndata[''priority''] = ''high'' if qty >= 100 else ''normal''"
        },
        "next": "check_priority"
      },
      "check_priority": {
        "type": "branch",
        "condition": {
          "field": "priority",
          "operator": "eq",
          "value": "high"
        },
        "on_true": "set_expedited",
        "on_false": "set_standard"
      },
      "set_expedited": {
        "type": "action",
        "connector_id": "internal",
        "action_id": "transform_data",
        "config": {
          "set": {"expedited": true, "shipping_days": 1}
        },
        "next": "log_result"
      },
      "set_standard": {
        "type": "action",
        "connector_id": "internal",
        "action_id": "transform_data",
        "config": {
          "set": {"expedited": false, "shipping_days": 5}
        },
        "next": "log_result"
      },
      "log_result": {
        "type": "action",
        "connector_id": "internal",
        "action_id": "log",
        "config": {
          "message": "Order processed: priority={{priority}}, expedited={{expedited}}, shipping_days={{shipping_days}}"
        },
        "next": "end"
      }
    }
  }');
END $$;