import { useState } from 'react';
import { useConnectors } from '../hooks/useConnectors';
import { useConnections } from '../hooks/useConnections';
import { ConnectorIcon } from '../components/ConnectorIcon';
import { SchemaForm } from '../components/SchemaForm';
import { Modal } from '../components/Modal';
import { api } from '../api';
import type { Connector, ConnectionDetail } from '../types';

export function ConnectionsPage() {
  const { connectors } = useConnectors();
  const { connections, loading, error, refetch } = useConnections();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formConnectorId, setFormConnectorId] = useState('');
  const [formName, setFormName] = useState('');
  const [formConfig, setFormConfig] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const connectableConnectors = (connectors ?? []).filter(
    (c) => c.connection_schema?.properties && Object.keys(c.connection_schema.properties).length > 0
  );

  function openCreate() {
    setEditingId(null);
    setFormConnectorId(connectableConnectors[0]?.id ?? '');
    setFormName('');
    setFormConfig({});
    setFormError(null);
    setModalOpen(true);
  }

  async function openEdit(connectionId: string) {
    try {
      const detail: ConnectionDetail = await api.getConnection(connectionId);
      setEditingId(detail.id);
      setFormConnectorId(detail.connector_id);
      setFormName(detail.name);
      setFormConfig(detail.config);
      setFormError(null);
      setModalOpen(true);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Failed to load connection');
    }
  }

  async function handleSave() {
    if (!formName.trim()) {
      setFormError('Name is required');
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      if (editingId) {
        await api.updateConnection(editingId, formName, formConfig);
      } else {
        await api.createConnection(formConnectorId, formName, formConfig);
      }
      setModalOpen(false);
      refetch();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteConnection(id);
      setDeleteConfirmId(null);
      refetch();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Failed to delete');
    }
  }

  const selectedConnector = connectableConnectors.find((c) => c.id === formConnectorId);

  if (loading) return <p className="text-gray-500">Loading connections...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;

  // Group connections by connector_id
  const grouped: Record<string, typeof connections> = {};
  for (const conn of connections ?? []) {
    if (!grouped[conn.connector_id]) grouped[conn.connector_id] = [];
    grouped[conn.connector_id]!.push(conn);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Connections</h1>
        {connectableConnectors.length > 0 && (
          <button
            onClick={openCreate}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
          >
            New Connection
          </button>
        )}
      </div>

      {(connections ?? []).length === 0 ? (
        <p className="text-gray-500 text-sm">
          No connections yet. Create one to store reusable credentials for your connectors.
        </p>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([connectorId, conns]) => {
            const connector = (connectors ?? []).find((c) => c.id === connectorId);
            return (
              <div key={connectorId}>
                <div className="flex items-center gap-2 mb-2">
                  <ConnectorIcon connectorId={connectorId} />
                  <h2 className="text-sm font-semibold text-gray-700">
                    {connector?.name ?? connectorId}
                  </h2>
                </div>
                <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                  {(conns ?? []).map((conn) => (
                    <div
                      key={conn.id}
                      className="bg-white rounded border border-gray-200 p-4 flex flex-col justify-between"
                    >
                      <div>
                        <h3 className="font-medium text-sm">{conn.name}</h3>
                        <p className="text-xs text-gray-400 mt-1">
                          Created {new Date(conn.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <div className="flex gap-2 mt-3">
                        <button
                          onClick={() => openEdit(conn.id)}
                          className="text-xs text-blue-600 hover:underline"
                        >
                          Edit
                        </button>
                        {deleteConfirmId === conn.id ? (
                          <span className="text-xs">
                            <span className="text-red-600">Delete?</span>{' '}
                            <button
                              onClick={() => handleDelete(conn.id)}
                              className="text-red-600 font-medium hover:underline"
                            >
                              Yes
                            </button>
                            {' / '}
                            <button
                              onClick={() => setDeleteConfirmId(null)}
                              className="text-gray-500 hover:underline"
                            >
                              No
                            </button>
                          </span>
                        ) : (
                          <button
                            onClick={() => setDeleteConfirmId(conn.id)}
                            className="text-xs text-red-500 hover:underline"
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingId ? 'Edit Connection' : 'New Connection'}
      >
        <div className="space-y-4">
          {!editingId && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Connector</label>
              <select
                value={formConnectorId}
                onChange={(e) => {
                  setFormConnectorId(e.target.value);
                  setFormConfig({});
                }}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              >
                {connectableConnectors.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
          )}

          {editingId && selectedConnector && (
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <ConnectorIcon connectorId={formConnectorId} />
              {selectedConnector.name}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Connection Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="e.g. My GitHub Account"
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
            />
          </div>

          {selectedConnector && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Credentials</label>
              <SchemaForm
                schema={selectedConnector.connection_schema}
                values={formConfig}
                onChange={setFormConfig}
              />
            </div>
          )}

          {formError && (
            <p className="text-red-600 text-sm">{formError}</p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={() => setModalOpen(false)}
              className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Saving...' : editingId ? 'Update' : 'Create'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
