import { useState } from 'react';
import { Link } from 'react-router';
import { Modal } from './Modal';
import { JsonEditor } from './JsonEditor';
import { api } from '../api';
import type { InputDefinition } from '../types';

interface RunWorkflowDialogProps {
  open: boolean;
  onClose: () => void;
  workflowName: string;
  inputs?: InputDefinition[];
}

type State = { phase: 'input' } | { phase: 'submitting' } | { phase: 'success'; instanceId: string } | { phase: 'error'; message: string };

function buildDefaults(inputs: InputDefinition[]): Record<string, unknown> {
  const defaults: Record<string, unknown> = {};
  for (const inp of inputs) {
    if (inp.default !== undefined) {
      defaults[inp.name] = inp.default;
    } else if (inp.type === 'boolean') {
      defaults[inp.name] = false;
    } else {
      defaults[inp.name] = inp.type === 'number' ? undefined : '';
    }
  }
  return defaults;
}

export function RunWorkflowDialog({ open, onClose, workflowName, inputs }: RunWorkflowDialogProps) {
  const hasInputs = inputs && inputs.length > 0;
  const [json, setJson] = useState('{}');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, unknown>>(() =>
    hasInputs ? buildDefaults(inputs) : {}
  );
  const [useJsonMode, setUseJsonMode] = useState(false);
  const [state, setState] = useState<State>({ phase: 'input' });

  async function handleRun() {
    setJsonError(null);
    let data: object;

    if (!hasInputs || useJsonMode) {
      try {
        data = JSON.parse(json);
      } catch {
        setJsonError('Invalid JSON');
        return;
      }
    } else {
      // Validate required fields
      for (const inp of inputs) {
        if (inp.required && (formValues[inp.name] === undefined || formValues[inp.name] === '')) {
          setJsonError(`"${inp.name}" is required`);
          return;
        }
      }
      // Build data from form values, only include non-empty fields
      data = {};
      for (const inp of inputs) {
        const val = formValues[inp.name];
        if (val !== undefined && val !== '') {
          (data as Record<string, unknown>)[inp.name] = val;
        }
      }
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
    setFormValues(hasInputs ? buildDefaults(inputs) : {});
    setUseJsonMode(false);
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
          {hasInputs && !useJsonMode ? (
            <div>
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm text-gray-600">Provide workflow inputs:</p>
                <button
                  onClick={() => {
                    setJson(JSON.stringify(formValues, null, 2));
                    setUseJsonMode(true);
                  }}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Switch to JSON
                </button>
              </div>
              <div className="space-y-3">
                {inputs.map((inp) => (
                  <InputField
                    key={inp.name}
                    input={inp}
                    value={formValues[inp.name]}
                    onChange={(val) => setFormValues((v) => ({ ...v, [inp.name]: val }))}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm text-gray-600">Provide initial data (JSON):</p>
                {hasInputs && (
                  <button
                    onClick={() => setUseJsonMode(false)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Switch to Form
                  </button>
                )}
              </div>
              <JsonEditor
                value={json}
                onChange={setJson}
                error={jsonError}
                rows={6}
              />
            </div>
          )}

          {jsonError && !useJsonMode && (
            <p className="text-red-600 text-sm mt-2">{jsonError}</p>
          )}

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

function InputField({
  input,
  value,
  onChange,
}: {
  input: InputDefinition;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {input.name}
        {input.required && <span className="text-red-500 ml-0.5">*</span>}
        <span className="text-xs text-gray-400 ml-2">{input.type}</span>
      </label>

      {input.type === 'boolean' ? (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!value}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span className="text-gray-600">{value ? 'true' : 'false'}</span>
        </label>
      ) : input.type === 'number' ? (
        <input
          type="number"
          value={(value as number) ?? ''}
          onChange={(e) => onChange(e.target.value ? Number(e.target.value) : undefined)}
          className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
        />
      ) : (
        <input
          type="text"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
        />
      )}

      {input.description && (
        <p className="text-xs text-gray-500 mt-1">{input.description}</p>
      )}
    </div>
  );
}
