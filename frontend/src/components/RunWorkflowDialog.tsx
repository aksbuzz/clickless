import { useState } from 'react';
import { Link } from 'react-router';
import { Modal } from './Modal';
import { JsonEditor } from './JsonEditor';
import { api } from '../api';

interface RunWorkflowDialogProps {
  open: boolean;
  onClose: () => void;
  workflowName: string;
}

type State = { phase: 'input' } | { phase: 'submitting' } | { phase: 'success'; instanceId: string } | { phase: 'error'; message: string };

export function RunWorkflowDialog({ open, onClose, workflowName }: RunWorkflowDialogProps) {
  const [json, setJson] = useState('{}');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [state, setState] = useState<State>({ phase: 'input' });

  async function handleRun() {
    setJsonError(null);
    let data: object;
    try {
      data = JSON.parse(json);
    } catch {
      setJsonError('Invalid JSON');
      return;
    }

    setState({ phase: 'submitting' });
    try {
      const result = await api.runWorkflow(workflowName, data);
      setState({ phase: 'success', instanceId: result.instance_id });
    } catch (e) {
      setState({ phase: 'error', message: e instanceof Error ? e.message : 'Unknown error' });
    }
  }

  function handleClose() {
    setState({ phase: 'input' });
    setJson('{}');
    setJsonError(null);
    onClose();
  }

  return (
    <Modal open={open} onClose={handleClose} title={`Run ${workflowName}`}>
      {state.phase === 'success' ? (
        <div>
          <p className="text-green-700 text-sm mb-3">Workflow started successfully.</p>
          <div className="bg-green-50 border border-green-200 rounded p-3 text-sm">
            <span className="text-gray-600">Instance ID: </span>
            <Link
              to={`/instances/${state.instanceId}`}
              className="text-blue-600 hover:underline font-mono text-xs"
              onClick={handleClose}
            >
              {state.instanceId}
            </Link>
          </div>
          <button
            onClick={handleClose}
            className="mt-4 px-4 py-2 bg-gray-100 rounded text-sm hover:bg-gray-200"
          >
            Close
          </button>
        </div>
      ) : (
        <div>
          <p className="text-sm text-gray-600 mb-3">Provide initial data for the workflow (JSON):</p>
          <JsonEditor
            value={json}
            onChange={setJson}
            error={jsonError}
            rows={6}
          />

          {state.phase === 'error' && (
            <p className="text-red-600 text-sm mt-2">{state.message}</p>
          )}

          <div className="flex justify-end gap-2 mt-4">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleRun}
              disabled={state.phase === 'submitting'}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {state.phase === 'submitting' ? 'Starting...' : 'Run Workflow'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
