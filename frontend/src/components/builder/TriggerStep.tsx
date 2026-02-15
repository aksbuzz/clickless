import { ConnectorIcon } from '../ConnectorIcon';
import { SchemaForm } from '../SchemaForm';
import type { Connector, TriggerConfig } from '../../types';

interface TriggerStepProps {
  connectors: Connector[];
  trigger: TriggerConfig | null;
  onChange: (trigger: TriggerConfig) => void;
}

export function TriggerStep({ connectors, trigger, onChange }: TriggerStepProps) {
  const triggerConnectors = connectors.filter((c) => c.triggers.length > 0);
  const selectedConnector = triggerConnectors.find((c) => c.id === trigger?.connector_id);
  const selectedTrigger = selectedConnector?.triggers.find((t) => t.id === trigger?.trigger_id);

  function handleConnectorSelect(connectorId: string) {
    const connector = triggerConnectors.find((c) => c.id === connectorId);
    if (!connector || connector.triggers.length === 0) return;
    onChange({
      connector_id: connectorId,
      trigger_id: connector.triggers[0].id,
      config: {},
    });
  }

  function handleTriggerSelect(triggerId: string) {
    if (!trigger) return;
    onChange({ ...trigger, trigger_id: triggerId, config: {} });
  }

  function handleConfigChange(config: Record<string, unknown>) {
    if (!trigger) return;
    onChange({ ...trigger, config });
  }

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Select Trigger</h3>

      <div className="grid gap-2 md:grid-cols-3 mb-4">
        {triggerConnectors.map((c) => (
          <button
            key={c.id}
            onClick={() => handleConnectorSelect(c.id)}
            className={`flex items-center gap-2 p-3 rounded border text-left text-sm ${
              trigger?.connector_id === c.id
                ? 'border-blue-500 bg-blue-50'
                : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            <ConnectorIcon connectorId={c.id} />
            <div>
              <div className="font-medium">{c.name}</div>
              <div className="text-xs text-gray-500">{c.triggers.length} trigger(s)</div>
            </div>
          </button>
        ))}
      </div>

      {selectedConnector && selectedConnector.triggers.length > 1 && (
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Trigger Event</label>
          <select
            value={trigger?.trigger_id ?? ''}
            onChange={(e) => handleTriggerSelect(e.target.value)}
            className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
          >
            {selectedConnector.triggers.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
      )}

      {selectedTrigger && (
        <div className="bg-gray-50 rounded border border-gray-200 p-4">
          <p className="text-sm text-gray-600 mb-3">{selectedTrigger.description}</p>
          <SchemaForm
            schema={selectedTrigger.config_schema}
            values={(trigger?.config as Record<string, unknown>) ?? {}}
            onChange={handleConfigChange}
          />
        </div>
      )}
    </div>
  );
}
