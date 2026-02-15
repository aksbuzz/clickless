import { useCallback, useState } from 'react';
import { useParams, Link } from 'react-router';
import { api } from '../api';
import { usePolling } from '../hooks/usePolling';
import { WorkflowGraph } from '../components/WorkflowGraph';
import { RunWorkflowDialog } from '../components/RunWorkflowDialog';
import { timeAgo } from '../utils';

export function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>();
  const fetcher = useCallback(() => api.getWorkflow(id!), [id]);
  const { data: workflow, loading, error } = usePolling(fetcher, 30_000);
  const [showJson, setShowJson] = useState(false);
  const [showRun, setShowRun] = useState(false);

  if (loading) return <p className="text-gray-500">Loading workflow...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;
  if (!workflow) return <p className="text-gray-500">Workflow not found.</p>;

  const version = workflow.active_version;
  const definition = version?.definition;

  return (
    <div>
      <Link to="/workflows" className="text-sm text-blue-600 hover:underline mb-4 inline-block">
        &larr; Back to Workflows
      </Link>

      <div className="bg-white rounded border border-gray-200 p-4 mb-6">
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-xl font-semibold">{workflow.name}</h1>
          <div className="flex gap-2">
            <button
              onClick={() => setShowRun(true)}
              className="px-3 py-1.5 text-sm bg-green-600 text-white rounded hover:bg-green-700"
            >
              Run
            </button>
            <Link
              to={`/workflows/${id}/edit`}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50"
            >
              Edit
            </Link>
            <Link
              to={`/instances?workflow_id=${id}`}
              className="px-3 py-1.5 text-sm text-blue-600 border border-blue-200 rounded hover:bg-blue-50"
            >
              Instances
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm text-gray-600">
          <div>Version: <span className="text-gray-900">{version?.version ?? '—'}</span></div>
          <div>Created: <span className="text-gray-900">{timeAgo(workflow.created_at)}</span></div>
          {definition?.description && (
            <div className="col-span-2">Description: <span className="text-gray-900">{definition.description}</span></div>
          )}
        </div>

        {definition && (
          <div className="mt-3">
            <div className="text-sm text-gray-600">
              Trigger: <span className="text-gray-900 font-mono text-xs">
                {definition.trigger.connector_id}/{definition.trigger.trigger_id}
              </span>
            </div>
            <div className="text-sm text-gray-600">
              Steps: <span className="text-gray-900">{Object.keys(definition.steps).length}</span>
            </div>
          </div>
        )}
      </div>

      {definition && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-3">Workflow Graph</h2>
          <WorkflowGraph definition={definition} />
        </div>
      )}

      {definition && (
        <div>
          <button
            onClick={() => setShowJson(!showJson)}
            className="text-sm text-blue-600 hover:underline mb-2"
          >
            {showJson ? 'Hide' : 'Show'} Definition JSON
          </button>
          {showJson && (
            <pre className="bg-gray-50 border border-gray-200 rounded p-3 text-xs overflow-auto max-h-96">
              {JSON.stringify(definition, null, 2)}
            </pre>
          )}
        </div>
      )}

      <RunWorkflowDialog
        open={showRun}
        onClose={() => setShowRun(false)}
        workflowName={workflow.name}
      />
    </div>
  );
}
