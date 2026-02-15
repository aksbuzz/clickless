import { useState } from 'react';
import { useConnectors } from '../hooks/useConnectors';
import { ConnectorIcon } from '../components/ConnectorIcon';
import type { ConfigSchema } from '../types';

export function ConnectorsPage() {
  const { connectors, loading, error } = useConnectors();
  const [search, setSearch] = useState('');
  const [expandedSchemas, setExpandedSchemas] = useState<Set<string>>(new Set());

  if (loading) return <p className="text-gray-500">Loading connectors...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;
  if (!connectors) return null;

  const filtered = search
    ? connectors.filter((c) =>
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.id.toLowerCase().includes(search.toLowerCase()) ||
        c.description.toLowerCase().includes(search.toLowerCase())
      )
    : connectors;

  function toggleSchema(key: string) {
    setExpandedSchemas((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Connectors</h1>

      <input
        type="text"
        placeholder="Search connectors..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full max-w-sm border border-gray-300 rounded px-3 py-2 text-sm mb-6 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {filtered.map((connector) => (
          <div key={connector.id} className="bg-white rounded border border-gray-200 p-4">
            <div className="flex items-center gap-3 mb-3">
              <ConnectorIcon connectorId={connector.id} />
              <div>
                <h3 className="font-medium text-sm">{connector.name}</h3>
                <p className="text-xs text-gray-500">{connector.id}</p>
              </div>
            </div>
            <p className="text-sm text-gray-600 mb-3">{connector.description}</p>

            {connector.triggers.length > 0 && (
              <div className="mb-3">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Triggers</h4>
                {connector.triggers.map((t) => {
                  const schemaKey = `${connector.id}:trigger:${t.id}`;
                  return (
                    <div key={t.id} className="mb-1">
                      <button
                        onClick={() => toggleSchema(schemaKey)}
                        className="text-sm text-left w-full hover:bg-gray-50 rounded px-2 py-1"
                      >
                        <span className="font-medium">{t.name}</span>
                        <span className="text-gray-400 ml-1 text-xs">{t.id}</span>
                      </button>
                      {expandedSchemas.has(schemaKey) && (
                        <div className="ml-2 pl-2 border-l border-gray-200 mt-1 mb-2">
                          <p className="text-xs text-gray-500 mb-2">{t.description}</p>
                          <SchemaDisplay schema={t.config_schema} />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {connector.actions.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Actions</h4>
                {connector.actions.map((a) => {
                  const schemaKey = `${connector.id}:action:${a.id}`;
                  return (
                    <div key={a.id} className="mb-1">
                      <button
                        onClick={() => toggleSchema(schemaKey)}
                        className="text-sm text-left w-full hover:bg-gray-50 rounded px-2 py-1"
                      >
                        <span className="font-medium">{a.name}</span>
                        <span className="text-gray-400 ml-1 text-xs">{a.id}</span>
                      </button>
                      {expandedSchemas.has(schemaKey) && (
                        <div className="ml-2 pl-2 border-l border-gray-200 mt-1 mb-2">
                          <p className="text-xs text-gray-500 mb-2">{a.description}</p>
                          <SchemaDisplay schema={a.config_schema} />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <p className="text-gray-500 text-sm">No connectors match your search.</p>
      )}
    </div>
  );
}

function SchemaDisplay({ schema }: { schema: ConfigSchema }) {
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  const entries = Object.entries(properties);

  if (entries.length === 0) {
    return <p className="text-xs text-gray-400 italic">No configuration fields.</p>;
  }

  return (
    <table className="text-xs w-full">
      <thead>
        <tr className="text-left text-gray-500">
          <th className="pb-1 pr-3 font-medium">Field</th>
          <th className="pb-1 pr-3 font-medium">Type</th>
          <th className="pb-1 font-medium">Description</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([key, prop]) => (
          <tr key={key} className="border-t border-gray-100">
            <td className="py-1 pr-3 font-mono">
              {key}
              {required.has(key) && <span className="text-red-500">*</span>}
            </td>
            <td className="py-1 pr-3 text-gray-500">{prop.type ?? 'string'}</td>
            <td className="py-1 text-gray-500">{prop.description ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
