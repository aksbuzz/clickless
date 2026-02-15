import { WorkflowGraph } from '../WorkflowGraph';
import type { WorkflowDefinition } from '../../types';

interface ReviewStepProps {
  definition: WorkflowDefinition;
}

export function ReviewStep({ definition }: ReviewStepProps) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Review Workflow</h3>

      <div className="mb-6">
        <h4 className="text-xs font-medium text-gray-500 mb-2">GRAPH PREVIEW</h4>
        <WorkflowGraph definition={definition} />
      </div>

      <div>
        <h4 className="text-xs font-medium text-gray-500 mb-2">DEFINITION JSON</h4>
        <pre className="bg-gray-50 border border-gray-200 rounded p-3 text-xs overflow-auto max-h-80">
          {JSON.stringify(definition, null, 2)}
        </pre>
      </div>
    </div>
  );
}
