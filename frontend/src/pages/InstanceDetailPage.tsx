import { useCallback, useState } from 'react';
import { useParams, Link } from 'react-router';
import { api } from '../api';
import { usePolling } from '../hooks/usePolling';
import { StatusBadge } from '../components/StatusBadge';
import { StepTimeline } from '../components/StepTimeline';
import { SendEventDialog } from '../components/SendEventDialog';
import { timeAgo } from '../utils';

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

export function InstanceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [showData, setShowData] = useState(false);
  const [isTerminal, setIsTerminal] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [showEventDialog, setShowEventDialog] = useState(false);

  const instanceFetcher = useCallback(async () => {
    const result = await api.getInstance(id!);
    setIsTerminal(TERMINAL.has(result.status));
    return result;
  }, [id]);
  const stepsFetcher = useCallback(() => api.getInstanceSteps(id!), [id]);

  const { data: instance, loading: instanceLoading, error: instanceError, refresh } = usePolling(instanceFetcher, 3_000, !isTerminal);
  const { data: steps, loading: stepsLoading } = usePolling(stepsFetcher, 3_000, !isTerminal);

  async function handleCancel() {
    setCancelError(null);
    setCancelling(true);
    try {
      await api.cancelInstance(id!);
      refresh();
    } catch (e) {
      setCancelError(e instanceof Error ? e.message : 'Failed to cancel');
    } finally {
      setCancelling(false);
    }
  }

  if (instanceLoading) return <p className="text-gray-500">Loading instance...</p>;
  if (instanceError) return <p className="text-red-600">Error: {instanceError}</p>;
  if (!instance) return <p className="text-gray-500">Instance not found.</p>;

  const canCancel = !TERMINAL.has(instance.status);
  const canSendEvent = instance.status === 'running' && instance.current_step;

  return (
    <div>
      <Link to="/instances" className="text-sm text-blue-600 hover:underline mb-4 inline-block">
        &larr; Back to Instances
      </Link>

      <div className="bg-white rounded border border-gray-200 p-4 mb-6">
        <div className="flex items-center gap-3 mb-3">
          <h1 className="text-lg font-semibold font-mono">{instance.id}</h1>
          <StatusBadge status={instance.status} />
        </div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm text-gray-600">
          <div>Current Step: <span className="text-gray-900">{instance.current_step ?? '—'}</span></div>
          <div>Attempts: <span className="text-gray-900">{instance.current_step_attempts}</span></div>
          <div>Created: <span className="text-gray-900">{timeAgo(instance.created_at)}</span></div>
          <div>Updated: <span className="text-gray-900">{timeAgo(instance.updated_at)}</span></div>
        </div>

        {(canCancel || canSendEvent) && (
          <div className="flex gap-2 mt-4">
            {canCancel && (
              <button
                onClick={handleCancel}
                disabled={cancelling}
                className="px-3 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
              >
                {cancelling ? 'Cancelling...' : 'Cancel Instance'}
              </button>
            )}
            {canSendEvent && (
              <button
                onClick={() => setShowEventDialog(true)}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Send Event
              </button>
            )}
          </div>
        )}
        {cancelError && <p className="text-red-600 text-sm mt-2">{cancelError}</p>}

        <div className="mt-4">
          <button
            onClick={() => setShowData(!showData)}
            className="text-sm text-blue-600 hover:underline"
          >
            {showData ? 'Hide' : 'Show'} Instance Data
          </button>
          {showData && (
            <pre className="mt-2 p-3 bg-gray-50 rounded text-xs overflow-auto max-h-60 border border-gray-200">
              {JSON.stringify(instance.data, null, 2)}
            </pre>
          )}
        </div>
      </div>

      <h2 className="text-lg font-semibold mb-3">Step Executions</h2>
      {stepsLoading ? (
        <p className="text-gray-500">Loading steps...</p>
      ) : (
        <StepTimeline steps={steps ?? []} />
      )}

      <SendEventDialog
        open={showEventDialog}
        onClose={() => {
          setShowEventDialog(false);
          refresh();
        }}
        instanceId={id!}
      />
    </div>
  );
}
