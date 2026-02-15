import { useCallback } from 'react';
import { Link, useSearchParams } from 'react-router';
import { api } from '../api';
import { usePolling } from '../hooks/usePolling';
import { StatusBadge } from '../components/StatusBadge';
import { timeAgo, truncateId } from '../utils';
import type { InstanceStatus } from '../types';

const STATUSES: Array<InstanceStatus | 'all'> = ['all', 'pending', 'running', 'completed', 'failed', 'cancelled'];

export function InstancesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const statusFilter = searchParams.get('status') || 'all';
  const workflowId = searchParams.get('workflow_id') || '';

  const fetcher = useCallback(() => {
    const params = new URLSearchParams();
    if (statusFilter !== 'all') params.set('status', statusFilter);
    if (workflowId) params.set('workflow_id', workflowId);
    return api.getInstances(params);
  }, [statusFilter, workflowId]);

  const { data: instances, loading, error } = usePolling(fetcher, 5_000);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === 'all') {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setSearchParams(next);
  };

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Instances</h1>

      <div className="flex gap-2 mb-4 items-center flex-wrap">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setFilter('status', s)}
            className={`px-3 py-1 rounded text-sm border ${
              statusFilter === s
                ? 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-100'
            }`}
          >
            {s}
          </button>
        ))}
        {workflowId && (
          <button
            onClick={() => setFilter('workflow_id', '')}
            className="ml-2 text-xs text-gray-500 hover:text-gray-800"
          >
            Clear workflow filter
          </button>
        )}
      </div>

      {loading && <p className="text-gray-500">Loading instances...</p>}
      {error && <p className="text-red-600">Error: {error}</p>}
      {!loading && instances && instances.length === 0 && (
        <p className="text-gray-500">No instances found.</p>
      )}

      {instances && instances.length > 0 && (
        <div className="bg-white rounded border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-600">
              <tr>
                <th className="px-4 py-3 font-medium">Instance ID</th>
                <th className="px-4 py-3 font-medium">Workflow</th>
                <th className="px-4 py-3 font-medium">Version</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Current Step</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {instances.map((inst) => (
                <tr key={inst.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link to={`/instances/${inst.id}`} className="text-blue-600 hover:underline font-mono">
                      {truncateId(inst.id)}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{inst.workflow_name}</td>
                  <td className="px-4 py-3">{inst.version}</td>
                  <td className="px-4 py-3"><StatusBadge status={inst.status} /></td>
                  <td className="px-4 py-3 text-gray-500">{inst.current_step ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-500">{timeAgo(inst.created_at)}</td>
                  <td className="px-4 py-3 text-gray-500">{timeAgo(inst.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
