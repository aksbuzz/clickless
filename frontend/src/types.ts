// --- Existing types ---

export interface Workflow {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  version_id: string | null;
  version: number | null;
  is_active: boolean | null;
}

export interface Instance {
  id: string;
  status: InstanceStatus;
  current_step: string | null;
  created_at: string;
  updated_at: string;
  workflow_name: string;
  version: number;
}

export interface InstanceDetail {
  id: string;
  workflow_version_id: string;
  status: InstanceStatus;
  current_step: string | null;
  current_step_attempts: number;
  data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface StepExecution {
  id: string;
  step_name: string;
  status: "pending" | "running" | "completed" | "failed";
  attempts: number;
  started_at: string;
  completed_at: string | null;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error_details: string | null;
}

export type InstanceStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

// --- Connector types (from GET /connectors) ---

export interface SchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  enum?: string[];
  default?: unknown;
  minimum?: number;
  maximum?: number;
  items?: { type: string };
  additionalProperties?: { type: string };
}

export interface ConfigSchema {
  type: "object";
  properties?: Record<string, SchemaProperty>;
  required?: string[];
}

export interface TriggerDefinition {
  id: string;
  name: string;
  description: string;
  config_schema: ConfigSchema;
}

export interface ActionDefinition {
  id: string;
  name: string;
  description: string;
  config_schema: ConfigSchema;
}

export interface Connector {
  id: string;
  name: string;
  description: string;
  triggers: TriggerDefinition[];
  actions: ActionDefinition[];
  connection_schema: ConfigSchema;
}

// --- Connection types ---

export interface Connection {
  id: string;
  connector_id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface ConnectionDetail extends Connection {
  config: Record<string, unknown>;
}

// --- Workflow detail (from GET /workflows/:id) ---

export interface WorkflowVersion {
  id: string;
  version: number;
  definition: WorkflowDefinition;
  is_active: boolean;
  created_at: string;
}

export interface WorkflowDetail {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  active_version: WorkflowVersion | null;
}

// --- Workflow definition structure ---

export interface TriggerConfig {
  connector_id: string;
  trigger_id: string;
  config: Record<string, unknown>;
}

export interface ActionStep {
  type: "action";
  connector_id: string;
  action_id: string;
  connection_id?: string;
  config: Record<string, unknown>;
  next: string;
  retry?: { max_attempts: number; delay_seconds: number };
}

export interface BranchStep {
  type: "branch";
  condition: { field: string; operator: string; value?: unknown };
  on_true: string;
  on_false: string;
}

export interface DelayStep {
  type: "delay";
  duration_seconds: number;
  next: string;
}

export interface WaitForEventStep {
  type: "wait_for_event";
  event_name: string;
  timeout_seconds?: number;
  next: string;
}

export type StepDefinition = ActionStep | BranchStep | DelayStep | WaitForEventStep;

export interface WorkflowDefinition {
  description?: string;
  trigger: TriggerConfig;
  start_at: string;
  steps: Record<string, StepDefinition>;
}

// --- Builder draft (client-side only) ---

export interface DraftStep {
  key: string;
  definition: StepDefinition;
}

export interface WorkflowDraft {
  name: string;
  description: string;
  trigger: TriggerConfig | null;
  steps: DraftStep[];
}

// --- API response types ---

export interface CreateWorkflowResponse {
  workflow_id: string;
  version_id: string;
  version: number;
}

export interface CreateVersionResponse {
  version_id: string;
  version: number;
}

export interface RunWorkflowResponse {
  message: string;
  instance_id: string;
}

export interface CancelInstanceResponse {
  message: string;
  instance_id: string;
}

export interface SendEventResponse {
  message: string;
  instance_id: string;
  step: string;
}

export interface CreateConnectionResponse {
  connection_id: string;
}

export interface MessageResponse {
  message: string;
}
