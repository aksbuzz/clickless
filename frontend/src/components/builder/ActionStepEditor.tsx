import { ConnectorIcon } from '../ConnectorIcon';
import { SchemaForm } from '../SchemaForm';
import type { Connector, Connection, StepDefinition, ActionStep, ConfigSchema } from '../../types';

interface ActionStepEditorProps {
  connectors: Connector[];
  connections: Connection[];
  stepKey: string;
  definition: StepDefinition;
  allStepKeys: string[];
  onKeyChange: (newKey: string) => void;
  onChange: (definition: StepDefinition) => void;
  onRemove: () => void;
}

const STEP_TYPES = [
  { value: 'action', label: 'Action' },
  { value: 'branch', label: 'Branch (If/Else)' },
  { value: 'delay', label: 'Delay' },
  { value: 'wait_for_event', label: 'Wait for Event' },
] as const;

const OPERATORS = [
  { value: 'eq', label: '= (equals)' },
  { value: 'neq', label: '!= (not equals)' },
  { value: 'gt', label: '> (greater than)' },
  { value: 'gte', label: '>= (greater or equal)' },
  { value: 'lt', label: '< (less than)' },
  { value: 'lte', label: '<= (less or equal)' },
  { value: 'contains', label: 'contains' },
  { value: 'exists', label: 'exists' },
];

function makeDefault(type: string): StepDefinition {
  switch (type) {
    case 'branch':
      return { type: 'branch', condition: { field: '', operator: 'eq', value: '' }, on_true: 'end', on_false: 'end' };
    case 'delay':
      return { type: 'delay', duration_seconds: 5, next: 'end' };
    case 'wait_for_event':
      return { type: 'wait_for_event', event_name: '', next: 'end' };
    default:
      return { type: 'action', connector_id: '', action_id: '', config: {}, next: 'end' };
  }
}

export function ActionStepEditor({
  connectors,
  connections,
  stepKey,
  definition,
  allStepKeys,
  onKeyChange,
  onChange,
  onRemove,
}: ActionStepEditorProps) {
  const actionConnectors = connectors.filter((c) => c.actions.length > 0);
  const nextOptions = [...allStepKeys.filter((k) => k !== stepKey), 'end'];

  function handleTypeChange(newType: string) {
    onChange(makeDefault(newType));
  }

  return (
    <div className="bg-white rounded border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <input
          type="text"
          value={stepKey}
          onChange={(e) => onKeyChange(e.target.value.replace(/\s+/g, '_'))}
          className="font-medium text-sm border-b border-transparent hover:border-gray-300 focus:border-blue-500 focus:outline-none px-1 py-0.5"
        />
        <button onClick={onRemove} className="text-gray-400 hover:text-red-600 text-sm">
          Remove
        </button>
      </div>

      <div className="mb-3">
        <label className="block text-xs font-medium text-gray-500 mb-1">Step Type</label>
        <select
          value={definition.type}
          onChange={(e) => handleTypeChange(e.target.value)}
          className="border border-gray-300 rounded px-3 py-1.5 text-sm"
        >
          {STEP_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      {definition.type === 'action' && (
        <ActionConfig
          connectors={actionConnectors}
          connections={connections}
          definition={definition}
          nextOptions={nextOptions}
          onChange={onChange}
        />
      )}

      {definition.type === 'branch' && (
        <BranchConfig
          definition={definition}
          nextOptions={nextOptions}
          onChange={onChange}
        />
      )}

      {definition.type === 'delay' && (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Duration (seconds)</label>
            <input
              type="number"
              min={1}
              value={definition.duration_seconds}
              onChange={(e) => onChange({ ...definition, duration_seconds: Number(e.target.value) })}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-32"
            />
          </div>
          <NextStepSelect
            value={definition.next}
            options={nextOptions}
            onChange={(next) => onChange({ ...definition, next })}
          />
        </div>
      )}

      {definition.type === 'wait_for_event' && (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Event Name</label>
            <input
              type="text"
              value={definition.event_name}
              onChange={(e) => onChange({ ...definition, event_name: e.target.value })}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full"
              placeholder="e.g. approval"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Timeout (seconds, optional)</label>
            <input
              type="number"
              min={0}
              value={definition.timeout_seconds ?? ''}
              onChange={(e) =>
                onChange({
                  ...definition,
                  timeout_seconds: e.target.value ? Number(e.target.value) : undefined,
                })
              }
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-32"
            />
          </div>
          <NextStepSelect
            value={definition.next}
            options={nextOptions}
            onChange={(next) => onChange({ ...definition, next })}
          />
        </div>
      )}
    </div>
  );
}

function hasConnectionSupport(connector: Connector): boolean {
  return !!(
    connector.connection_schema?.properties &&
    Object.keys(connector.connection_schema.properties).length > 0
  );
}

function filterSchemaForConnection(schema: ConfigSchema, connectionSchema: ConfigSchema): ConfigSchema {
  const connectionKeys = new Set(Object.keys(connectionSchema.properties ?? {}));
  return {
    ...schema,
    properties: Object.fromEntries(
      Object.entries(schema.properties ?? {}).filter(([key]) => !connectionKeys.has(key))
    ),
    required: (schema.required ?? []).filter((key) => !connectionKeys.has(key)),
  };
}

function ActionConfig({
  connectors,
  connections,
  definition,
  nextOptions,
  onChange,
}: {
  connectors: Connector[];
  connections: Connection[];
  definition: ActionStep;
  nextOptions: string[];
  onChange: (d: StepDefinition) => void;
}) {
  const selectedConnector = connectors.find((c) => c.id === definition.connector_id);
  const selectedAction = selectedConnector?.actions.find((a) => a.id === definition.action_id);

  const supportsConnections = selectedConnector && hasConnectionSupport(selectedConnector);
  const connectorConnections = connections.filter((c) => c.connector_id === definition.connector_id);

  // Build filtered schema that hides connection fields when a connection is selected
  const displaySchema = selectedAction
    ? definition.connection_id && selectedConnector
      ? filterSchemaForConnection(selectedAction.config_schema, selectedConnector.connection_schema)
      : selectedAction.config_schema
    : undefined;

  function handleConnectorChange(connectorId: string) {
    const connector = connectors.find((c) => c.id === connectorId);
    const firstAction = connector?.actions[0];
    onChange({
      ...definition,
      connector_id: connectorId,
      action_id: firstAction?.id ?? '',
      connection_id: undefined,
      config: {},
    });
  }

  function handleConnectionChange(connectionId: string) {
    if (connectionId === '') {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { connection_id: _, ...rest } = definition;
      onChange({ ...rest } as ActionStep);
    } else {
      onChange({ ...definition, connection_id: connectionId });
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Connector</label>
        <div className="flex flex-wrap gap-1.5">
          {connectors.map((c) => (
            <button
              key={c.id}
              onClick={() => handleConnectorChange(c.id)}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded border text-xs ${
                definition.connector_id === c.id
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <ConnectorIcon connectorId={c.id} />
              {c.name}
            </button>
          ))}
        </div>
      </div>

      {supportsConnections && (
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Connection</label>
          <select
            value={definition.connection_id ?? ''}
            onChange={(e) => handleConnectionChange(e.target.value)}
            className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full"
          >
            <option value="">(None - enter credentials manually)</option>
            {connectorConnections.map((conn) => (
              <option key={conn.id} value={conn.id}>{conn.name}</option>
            ))}
          </select>
          {connectorConnections.length === 0 && (
            <p className="text-xs text-gray-400 mt-1">
              No connections for {selectedConnector!.name}.{' '}
              <a href="/connections" className="text-blue-500 hover:underline">Create one</a>
            </p>
          )}
        </div>
      )}

      {selectedConnector && (
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Action</label>
          <select
            value={definition.action_id}
            onChange={(e) => onChange({ ...definition, action_id: e.target.value, config: {} })}
            className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full"
          >
            {selectedConnector.actions.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </div>
      )}

      {selectedAction && displaySchema && (
        <div className="bg-gray-50 rounded border border-gray-200 p-3">
          <p className="text-xs text-gray-500 mb-2">{selectedAction.description}</p>
          {definition.connection_id && (
            <p className="text-xs text-green-600 mb-2">
              Credentials provided by connection.
            </p>
          )}
          <SchemaForm
            schema={displaySchema}
            values={(definition.config as Record<string, unknown>) ?? {}}
            onChange={(config) => onChange({ ...definition, config })}
          />
        </div>
      )}

      <NextStepSelect
        value={definition.next}
        options={nextOptions}
        onChange={(next) => onChange({ ...definition, next })}
      />

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-1.5 text-xs text-gray-500">
          <input
            type="checkbox"
            checked={!!definition.retry}
            onChange={(e) =>
              onChange({
                ...definition,
                retry: e.target.checked ? { max_attempts: 3, delay_seconds: 5 } : undefined,
              })
            }
          />
          Enable retry
        </label>
        {definition.retry && (
          <>
            <input
              type="number"
              min={1}
              value={definition.retry.max_attempts}
              onChange={(e) =>
                onChange({ ...definition, retry: { ...definition.retry!, max_attempts: Number(e.target.value) } })
              }
              className="border border-gray-300 rounded px-2 py-1 text-xs w-16"
            />
            <span className="text-xs text-gray-500">attempts,</span>
            <input
              type="number"
              min={1}
              value={definition.retry.delay_seconds}
              onChange={(e) =>
                onChange({ ...definition, retry: { ...definition.retry!, delay_seconds: Number(e.target.value) } })
              }
              className="border border-gray-300 rounded px-2 py-1 text-xs w-16"
            />
            <span className="text-xs text-gray-500">sec delay</span>
          </>
        )}
      </div>
    </div>
  );
}

function BranchConfig({
  definition,
  nextOptions,
  onChange,
}: {
  definition: Extract<StepDefinition, { type: 'branch' }>;
  nextOptions: string[];
  onChange: (d: StepDefinition) => void;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">Field (dot notation)</label>
        <input
          type="text"
          value={definition.condition.field}
          onChange={(e) =>
            onChange({ ...definition, condition: { ...definition.condition, field: e.target.value } })
          }
          placeholder="e.g. data.amount"
          className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Operator</label>
          <select
            value={definition.condition.operator}
            onChange={(e) =>
              onChange({ ...definition, condition: { ...definition.condition, operator: e.target.value } })
            }
            className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full"
          >
            {OPERATORS.map((op) => (
              <option key={op.value} value={op.value}>{op.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Value</label>
          <input
            type="text"
            value={String(definition.condition.value ?? '')}
            onChange={(e) => {
              const raw = e.target.value;
              let parsed: unknown = raw;
              if (raw === 'true') parsed = true;
              else if (raw === 'false') parsed = false;
              else if (raw !== '' && !isNaN(Number(raw))) parsed = Number(raw);
              onChange({ ...definition, condition: { ...definition.condition, value: parsed } });
            }}
            className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full"
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">If True →</label>
          <select
            value={definition.on_true}
            onChange={(e) => onChange({ ...definition, on_true: e.target.value })}
            className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full"
          >
            {nextOptions.map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">If False →</label>
          <select
            value={definition.on_false}
            onChange={(e) => onChange({ ...definition, on_false: e.target.value })}
            className="border border-gray-300 rounded px-3 py-1.5 text-sm w-full"
          >
            {nextOptions.map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

function NextStepSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">Next Step</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="border border-gray-300 rounded px-3 py-1.5 text-sm"
      >
        {options.map((k) => (
          <option key={k} value={k}>{k}</option>
        ))}
      </select>
    </div>
  );
}
