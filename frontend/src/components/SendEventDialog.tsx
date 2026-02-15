import { useState } from 'react';
import { Modal } from './Modal';
import { JsonEditor } from './JsonEditor';
import { api } from '../api';

interface SendEventDialogProps {
  open: boolean;
  onClose: () => void;
  instanceId: string;
}

export function SendEventDialog({ open, onClose, instanceId }: SendEventDialogProps) {
  const [json, setJson] = useState('{}');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSend() {
    setJsonError(null);
    setError(null);
    let data: object;
    try {
      data = JSON.parse(json);
    } catch {
      setJsonError('Invalid JSON');
      return;
    }

    setSubmitting(true);
    try {
      const result = await api.sendEvent(instanceId, data);
      setSuccess(`Event sent. Resuming step: ${result.step}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    setJson('{}');
    setJsonError(null);
    setError(null);
    setSuccess(null);
    onClose();
  }

  return (
    <Modal open={open} onClose={handleClose} title="Send Event">
      {success ? (
        <div>
          <p className="text-green-700 text-sm mb-4">{success}</p>
          <button
            onClick={handleClose}
            className="px-4 py-2 bg-gray-100 rounded text-sm hover:bg-gray-200"
          >
            Close
          </button>
        </div>
      ) : (
        <div>
          <p className="text-sm text-gray-600 mb-3">
            Send event data to resume the waiting workflow step:
          </p>
          <JsonEditor value={json} onChange={setJson} error={jsonError} rows={6} />

          {error && <p className="text-red-600 text-sm mt-2">{error}</p>}

          <div className="flex justify-end gap-2 mt-4">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSend}
              disabled={submitting}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting ? 'Sending...' : 'Send Event'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
