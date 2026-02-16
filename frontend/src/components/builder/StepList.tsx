import { ActionStepEditor } from './ActionStepEditor';
import type { Connector, Connection, DraftStep, StepDefinition } from '../../types';

interface StepListProps {
  connectors: Connector[];
  connections: Connection[];
  steps: DraftStep[];
  onChange: (steps: DraftStep[]) => void;
}

export function StepList({ connectors, connections, steps, onChange }: StepListProps) {
  const allStepKeys = steps.map((s) => s.key);

  function addStep() {
    const idx = steps.length + 1;
    let key = `step_${idx}`;
    let counter = 1;
    while (allStepKeys.includes(key)) {
      key = `step_${idx}_${counter}`;
      counter++;
    }
    const newStep: DraftStep = {
      key,
      definition: { type: 'action', connector_id: '', action_id: '', config: {}, next: 'end' },
    };

    // Auto-wire: update previous last step's next to point to this new step
    const updated = steps.map((s, i) => {
      if (i === steps.length - 1 && s.definition.type !== 'branch') {
        return { ...s, definition: { ...s.definition, next: key } as StepDefinition };
      }
      return s;
    });

    onChange([...updated, newStep]);
  }

  function updateStep(index: number, definition: StepDefinition) {
    const updated = [...steps];
    updated[index] = { ...updated[index], definition };
    onChange(updated);
  }

  function updateKey(index: number, newKey: string) {
    if (!newKey) return;
    const oldKey = steps[index].key;
    if (newKey === oldKey) return;
    if (allStepKeys.includes(newKey)) return;

    // Rename key and update all references in other steps
    const updated = steps.map((s, i) => {
      let def = i === index ? { ...s, key: newKey } : s;
      const d = def.definition;
      if (d.type === 'branch') {
        let changed = false;
        let on_true = d.on_true;
        let on_false = d.on_false;
        if (on_true === oldKey) { on_true = newKey; changed = true; }
        if (on_false === oldKey) { on_false = newKey; changed = true; }
        if (changed) def = { ...def, definition: { ...d, on_true, on_false } };
      } else if ('next' in d && d.next === oldKey) {
        def = { ...def, definition: { ...d, next: newKey } as StepDefinition };
      }
      return def;
    });
    onChange(updated);
  }

  function removeStep(index: number) {
    const removedKey = steps[index].key;
    const updated = steps
      .filter((_, i) => i !== index)
      .map((s) => {
        const d = s.definition;
        if (d.type === 'branch') {
          return {
            ...s,
            definition: {
              ...d,
              on_true: d.on_true === removedKey ? 'end' : d.on_true,
              on_false: d.on_false === removedKey ? 'end' : d.on_false,
            },
          };
        } else if ('next' in d && d.next === removedKey) {
          return { ...s, definition: { ...d, next: 'end' } as StepDefinition };
        }
        return s;
      });
    onChange(updated);
  }

  function moveStep(index: number, direction: -1 | 1) {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= steps.length) return;
    const updated = [...steps];
    [updated[index], updated[newIndex]] = [updated[newIndex], updated[index]];
    onChange(updated);
  }

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Workflow Steps</h3>

      <div className="space-y-3">
        {steps.map((step, i) => (
          <div key={step.key} className="relative">
            {steps.length > 1 && (
              <div className="absolute -left-8 top-4 flex flex-col gap-0.5">
                <button
                  onClick={() => moveStep(i, -1)}
                  disabled={i === 0}
                  className="text-gray-400 hover:text-gray-600 disabled:opacity-30 text-xs"
                >
                  ▲
                </button>
                <button
                  onClick={() => moveStep(i, 1)}
                  disabled={i === steps.length - 1}
                  className="text-gray-400 hover:text-gray-600 disabled:opacity-30 text-xs"
                >
                  ▼
                </button>
              </div>
            )}
            <ActionStepEditor
              connectors={connectors}
              connections={connections}
              stepKey={step.key}
              definition={step.definition}
              allStepKeys={allStepKeys}
              onKeyChange={(newKey) => updateKey(i, newKey)}
              onChange={(def) => updateStep(i, def)}
              onRemove={() => removeStep(i)}
            />
          </div>
        ))}
      </div>

      <button
        onClick={addStep}
        className="mt-3 px-4 py-2 border border-dashed border-gray-300 rounded text-sm text-gray-600 hover:border-gray-400 hover:text-gray-800 w-full"
      >
        + Add Step
      </button>
    </div>
  );
}
