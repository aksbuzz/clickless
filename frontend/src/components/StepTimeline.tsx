import { useState } from 'react';
import type { StepExecution } from '../types';
import { StatusBadge } from './StatusBadge';
import { timeAgo, formatDuration } from '../utils';

export function StepTimeline({ steps }: { steps: StepExecution[] }) {
  if (steps.length === 0) {
    return <p className="text-gray-500 text-sm">No steps executed yet.</p>;
  }

  return (
    <div className="relative pl-6">
      <div className="absolute left-2.5 top-0 bottom-0 w-px bg-gray-300" />
      {steps.map((step) => (
        <StepItem key={step.id} step={step} />
      ))}
    </div>
  );
}

function StepItem({ step }: { step: StepExecution }) {
  const [expanded, setExpanded] = useState(false);
  const duration = step.started_at && step.completed_at
    ? formatDuration(step.started_at, step.completed_at)
    : step.status === 'running' ? 'running...' : null;

  return (
    <div className="relative pb-6 last:pb-0">
      <div className="absolute -left-3.5 top-1 w-3 h-3 rounded-full border-2 border-white bg-gray-400" />
      <div className="bg-white rounded border border-gray-200 p-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{step.step_name}</span>
          <StatusBadge status={step.status} />
          {duration && <span className="text-xs text-gray-500">{duration}</span>}
          {step.attempts > 1 && (
            <span className="text-xs text-orange-600">{step.attempts} attempts</span>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-auto text-xs text-blue-600 hover:underline"
          >
            {expanded ? 'Collapse' : 'Details'}
          </button>
        </div>

        {step.error_details && (
          <p className="mt-2 text-xs text-red-600 bg-red-50 p-2 rounded">{step.error_details}</p>
        )}

        {expanded && (
          <div className="mt-3 space-y-2">
            <div className="text-xs text-gray-500">
              Started: {timeAgo(step.started_at)}
              {step.completed_at && <> &middot; Completed: {timeAgo(step.completed_at)}</>}
            </div>
            {step.input_data && (
              <details className="text-xs">
                <summary className="cursor-pointer text-gray-600">Input Data</summary>
                <pre className="mt-1 p-2 bg-gray-50 rounded overflow-auto max-h-40">
                  {JSON.stringify(step.input_data, null, 2)}
                </pre>
              </details>
            )}
            {step.output_data && (
              <details className="text-xs">
                <summary className="cursor-pointer text-gray-600">Output Data</summary>
                <pre className="mt-1 p-2 bg-gray-50 rounded overflow-auto max-h-40">
                  {JSON.stringify(step.output_data, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
