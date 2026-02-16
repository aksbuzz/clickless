import type {
  Workflow, Instance, InstanceDetail, StepExecution,
  Connector, WorkflowDetail, Connection, ConnectionDetail,
  CreateWorkflowResponse, CreateVersionResponse,
  RunWorkflowResponse, CancelInstanceResponse, SendEventResponse,
  CreateConnectionResponse, MessageResponse,
} from './types';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => null);
    const detail = errBody?.detail;
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.join('; ')
        : `${res.status} ${res.statusText}`;
    throw new Error(message);
  }
  return res.json();
}

async function put<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => null);
    const detail = errBody?.detail;
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.join('; ')
        : `${res.status} ${res.statusText}`;
    throw new Error(message);
  }
  return res.json();
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(path, { method: 'DELETE' });
  if (!res.ok) {
    const errBody = await res.json().catch(() => null);
    const detail = errBody?.detail;
    const message = typeof detail === 'string'
      ? detail
      : `${res.status} ${res.statusText}`;
    throw new Error(message);
  }
  return res.json();
}

export const api = {
  // Workflows
  getWorkflows: () =>
    get<Workflow[]>('/api/workflows'),
  getWorkflow: (id: string) =>
    get<WorkflowDetail>(`/api/workflows/${id}`),
  createWorkflow: (name: string, definition: object) =>
    post<CreateWorkflowResponse>('/api/workflows', { name, definition }),
  createVersion: (workflowId: string, definition: object) =>
    post<CreateVersionResponse>(`/api/workflows/${workflowId}/versions`, { definition }),

  // Execution
  runWorkflow: (name: string, data: object) =>
    post<RunWorkflowResponse>(`/api/workflows/${name}/run`, { data }),

  // Instances
  getInstances: (params?: URLSearchParams) =>
    get<Instance[]>(`/api/instances${params ? `?${params}` : ''}`),
  getInstance: (id: string) =>
    get<InstanceDetail>(`/api/instances/${id}`),
  getInstanceSteps: (id: string) =>
    get<StepExecution[]>(`/api/instances/${id}/steps`),
  cancelInstance: (id: string) =>
    post<CancelInstanceResponse>(`/api/instances/${id}/cancel`),
  sendEvent: (id: string, data: object) =>
    post<SendEventResponse>(`/api/instances/${id}/events`, { data }),

  // Connectors
  getConnectors: () =>
    get<Connector[]>('/api/connectors'),

  // Connections
  getConnections: (connectorId?: string) =>
    get<Connection[]>(`/api/connections${connectorId ? `?connector_id=${connectorId}` : ''}`),
  getConnection: (id: string) =>
    get<ConnectionDetail>(`/api/connections/${id}`),
  createConnection: (connectorId: string, name: string, config: object) =>
    post<CreateConnectionResponse>('/api/connections', { connector_id: connectorId, name, config }),
  updateConnection: (id: string, name: string, config: object) =>
    put<MessageResponse>(`/api/connections/${id}`, { name, config }),
  deleteConnection: (id: string) =>
    del<MessageResponse>(`/api/connections/${id}`),
};
