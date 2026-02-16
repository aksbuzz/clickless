import { useState, useCallback, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router';
import { api } from '../api';
import { useConnectors } from '../hooks/useConnectors';
import { useConnections } from '../hooks/useConnections';
import { TriggerStep } from '../components/builder/TriggerStep';
import { StepList } from '../components/builder/StepList';
import { ReviewStep } from '../components/builder/ReviewStep';
import type {
  WorkflowDraft, WorkflowDefinition, TriggerConfig, DraftStep, StepDefinition,
} from '../types';

const WIZARD_STEPS = ['Trigger', 'Steps', 'Review'] as const;

function emptyDraft(): WorkflowDraft {
  return { name: '', description: '', trigger: null, steps: [] };
}

function draftToDefinition(draft: WorkflowDraft): WorkflowDefinition {
  const steps: Record<string, StepDefinition> = {};
  for (const s of draft.steps) {
    steps[s.key] = s.definition;
  }
  return {
    description: draft.description || undefined,
    trigger: draft.trigger!,
    start_at: draft.steps[0]?.key ?? 'end',
    steps,
  };
}

function definitionToDraft(name: string, def: WorkflowDefinition): WorkflowDraft {
  // Walk steps in execution order starting from start_at
  const ordered: DraftStep[] = [];
  const visited = new Set<string>();

  function walk(key: string) {
    if (key === 'end' || visited.has(key)) return;
    const step = def.steps[key];
    if (!step) return;
    visited.add(key);
    ordered.push({ key, definition: step });

    if (step.type === 'branch') {
      walk(step.on_true);
      walk(step.on_false);
    } else {
      walk(step.next);
    }
  }

  walk(def.start_at);

  // Add any unvisited steps (disconnected)
  for (const key of Object.keys(def.steps)) {
    if (!visited.has(key)) {
      ordered.push({ key, definition: def.steps[key] });
    }
  }

  return {
    name,
    description: def.description ?? '',
    trigger: def.trigger,
    steps: ordered,
  };
}

export function WorkflowBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { connectors, loading: connectorsLoading } = useConnectors();
  const { connections } = useConnections();

  const isEdit = !!id;
  const [wizardStep, setWizardStep] = useState(0);
  const [draft, setDraft] = useState<WorkflowDraft>(emptyDraft());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editLoaded, setEditLoaded] = useState(false);

  // Load existing workflow for edit mode
  const loadWorkflow = useCallback(async () => {
    if (!id || editLoaded) return;
    try {
      const workflow = await api.getWorkflow(id);
      if (workflow.active_version?.definition) {
        setDraft(definitionToDraft(workflow.name, workflow.active_version.definition));
        setEditLoaded(true);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load workflow');
    }
  }, [id, editLoaded]);

  useEffect(() => {
    if (isEdit) loadWorkflow();
  }, [isEdit, loadWorkflow]);

  if (connectorsLoading) return <p className="text-gray-500">Loading connectors...</p>;
  if (!connectors) return <p className="text-red-600">Failed to load connectors.</p>;

  function handleTriggerChange(trigger: TriggerConfig) {
    setDraft((d) => ({ ...d, trigger }));
  }

  function handleStepsChange(steps: DraftStep[]) {
    setDraft((d) => ({ ...d, steps }));
  }

  function canProceed(): boolean {
    if (wizardStep === 0) return !!draft.trigger?.connector_id;
    if (wizardStep === 1) return draft.steps.length > 0;
    return true;
  }

  async function handleSave() {
    if (!draft.name.trim()) {
      setError('Workflow name is required');
      return;
    }
    if (!draft.trigger) {
      setError('Trigger is required');
      return;
    }
    if (draft.steps.length === 0) {
      setError('At least one step is required');
      return;
    }

    setError(null);
    setSaving(true);
    const definition = draftToDefinition(draft);

    try {
      if (isEdit) {
        await api.createVersion(id!, definition);
        navigate(`/workflows/${id}`);
      } else {
        const result = await api.createWorkflow(draft.name, definition);
        navigate(`/workflows/${result.workflow_id}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save workflow');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <Link to={isEdit ? `/workflows/${id}` : '/workflows'} className="text-sm text-blue-600 hover:underline mb-4 inline-block">
        &larr; {isEdit ? 'Back to Workflow' : 'Back to Workflows'}
      </Link>

      <h1 className="text-xl font-semibold mb-4">
        {isEdit ? `Edit: ${draft.name}` : 'Create Workflow'}
      </h1>

      {/* Wizard step indicator */}
      <div className="flex items-center gap-2 mb-6">
        {WIZARD_STEPS.map((label, i) => (
          <button
            key={label}
            onClick={() => i <= wizardStep && setWizardStep(i)}
            className={`px-3 py-1.5 rounded text-sm ${
              i === wizardStep
                ? 'bg-blue-600 text-white'
                : i < wizardStep
                  ? 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                  : 'bg-gray-100 text-gray-400'
            }`}
          >
            {i + 1}. {label}
          </button>
        ))}
      </div>

      {/* Workflow name & description */}
      {wizardStep === 2 && !isEdit && (
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Workflow Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={draft.name}
              onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value.replace(/\s+/g, '_') }))}
              placeholder="e.g. invoice_workflow"
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <input
              type="text"
              value={draft.description}
              onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
              placeholder="Optional description"
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
            />
          </div>
        </div>
      )}

      {/* Wizard content */}
      <div className="pl-8">
        {wizardStep === 0 && (
          <TriggerStep
            connectors={connectors}
            trigger={draft.trigger}
            onChange={handleTriggerChange}
          />
        )}

        {wizardStep === 1 && (
          <StepList
            connectors={connectors}
            connections={connections ?? []}
            steps={draft.steps}
            onChange={handleStepsChange}
          />
        )}

        {wizardStep === 2 && draft.trigger && draft.steps.length > 0 && (
          <ReviewStep definition={draftToDefinition(draft)} />
        )}
      </div>

      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Navigation buttons */}
      <div className="flex justify-between mt-6 pt-4 border-t border-gray-200">
        <button
          onClick={() => setWizardStep((s) => s - 1)}
          disabled={wizardStep === 0}
          className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-30"
        >
          Previous
        </button>

        {wizardStep < WIZARD_STEPS.length - 1 ? (
          <button
            onClick={() => setWizardStep((s) => s + 1)}
            disabled={!canProceed()}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            Next
          </button>
        ) : (
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : isEdit ? 'Save New Version' : 'Create Workflow'}
          </button>
        )}
      </div>
    </div>
  );
}
