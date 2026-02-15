import { useCallback } from 'react';
import { Link } from 'react-router';
import { api } from '../api';
import { usePolling } from '../hooks/usePolling';
import { timeAgo } from '../utils';

export function WorkflowsPage() {
  const fetcher = useCallback(() => api.getWorkflows(), []);
  const { data: workflows, loading, error } = usePolling(fetcher, 30_000);

  if (loading) return <p className="text-gray-500">Loading workflows...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Workflows</h1>
        <Link
          to="/workflows/new"
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
        >
          + Create Workflow
        </Link>
      </div>

      {!workflows || workflows.length === 0 ? (
        <div className="bg-white rounded border border-gray-200 p-8 text-center">
          <p className="text-gray-500 mb-3">No workflows yet.</p>
          <Link to="/workflows/new" className="text-blue-600 hover:underline text-sm">
            Create your first workflow
          </Link>
        </div>
      ) : (
        <div className="bg-white rounded border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-600">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Active Version</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium">Updated</th>
                <th className="px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {workflows.map((w) => (
                <tr key={w.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">
                    <Link to={`/workflows/${w.id}`} className="text-blue-600 hover:underline">
                      {w.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{w.version ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-500">{timeAgo(w.created_at)}</td>
                  <td className="px-4 py-3 text-gray-500">{timeAgo(w.updated_at)}</td>
                  <td className="px-4 py-3">
                    <Link
                      to={`/instances?workflow_id=${w.id}`}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      Instances
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
