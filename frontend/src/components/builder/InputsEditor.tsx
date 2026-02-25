import type { InputDefinition } from '../../types';

interface InputsEditorProps {
  inputs: InputDefinition[];
  onChange: (inputs: InputDefinition[]) => void;
}

const INPUT_TYPES = [
  { value: 'string', label: 'String' },
  { value: 'number', label: 'Number' },
  { value: 'boolean', label: 'Boolean' },
] as const;

function emptyInput(): InputDefinition {
  return { name: '', type: 'string', required: true };
}

export function InputsEditor({ inputs, onChange }: InputsEditorProps) {
  function handleAdd() {
    onChange([...inputs, emptyInput()]);
  }

  function handleRemove(index: number) {
    onChange(inputs.filter((_, i) => i !== index));
  }

  function handleChange(index: number, patch: Partial<InputDefinition>) {
    onChange(inputs.map((inp, i) => (i === index ? { ...inp, ...patch } : inp)));
  }

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-1">Workflow Inputs</h3>
      <p className="text-xs text-gray-500 mb-4">
        Define the inputs required when running this workflow. Reference them in step configs with{' '}
        <code className="bg-gray-100 px-1 rounded">{'{{input_name}}'}</code>.
      </p>

      {inputs.length === 0 ? (
        <p className="text-sm text-gray-400 italic mb-4">No inputs defined. Inputs are optional.</p>
      ) : (
        <div className="space-y-3 mb-4">
          {inputs.map((input, index) => {
            const nameConflict =
              input.name !== '' &&
              inputs.some((other, j) => j !== index && other.name === input.name);

            return (
              <div
                key={index}
                className="bg-white rounded border border-gray-200 p-3"
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1">
                    <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
                    <input
                      type="text"
                      value={input.name}
                      onChange={(e) =>
                        handleChange(index, { name: e.target.value.replace(/\s+/g, '_') })
                      }
                      placeholder="e.g. customer_email"
                      className={`w-full border rounded px-3 py-1.5 text-sm ${
                        nameConflict ? 'border-red-400' : 'border-gray-300'
                      }`}
                    />
                    {nameConflict && (
                      <p className="text-xs text-red-500 mt-0.5">Duplicate name</p>
                    )}
                  </div>

                  <div className="w-28">
                    <label className="block text-xs font-medium text-gray-500 mb-1">Type</label>
                    <select
                      value={input.type}
                      onChange={(e) =>
                        handleChange(index, {
                          type: e.target.value as InputDefinition['type'],
                          default: undefined,
                        })
                      }
                      className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                    >
                      {INPUT_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="pt-5">
                    <label className="flex items-center gap-1.5 text-xs text-gray-500">
                      <input
                        type="checkbox"
                        checked={input.required ?? false}
                        onChange={(e) => handleChange(index, { required: e.target.checked })}
                      />
                      Required
                    </label>
                  </div>

                  <button
                    onClick={() => handleRemove(index)}
                    className="pt-5 text-gray-400 hover:text-red-600 text-sm"
                  >
                    Remove
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-3 mt-2">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Description
                    </label>
                    <input
                      type="text"
                      value={input.description ?? ''}
                      onChange={(e) =>
                        handleChange(index, {
                          description: e.target.value || undefined,
                        })
                      }
                      placeholder="Optional description"
                      className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Default Value
                    </label>
                    {input.type === 'boolean' ? (
                      <select
                        value={
                          input.default === true
                            ? 'true'
                            : input.default === false
                              ? 'false'
                              : ''
                        }
                        onChange={(e) =>
                          handleChange(index, {
                            default:
                              e.target.value === ''
                                ? undefined
                                : e.target.value === 'true',
                          })
                        }
                        className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                      >
                        <option value="">No default</option>
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    ) : input.type === 'number' ? (
                      <input
                        type="number"
                        value={(input.default as number) ?? ''}
                        onChange={(e) =>
                          handleChange(index, {
                            default: e.target.value ? Number(e.target.value) : undefined,
                          })
                        }
                        placeholder="Optional"
                        className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                      />
                    ) : (
                      <input
                        type="text"
                        value={(input.default as string) ?? ''}
                        onChange={(e) =>
                          handleChange(index, {
                            default: e.target.value || undefined,
                          })
                        }
                        placeholder="Optional"
                        className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                      />
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <button
        onClick={handleAdd}
        className="px-3 py-1.5 text-sm border border-dashed border-gray-300 rounded hover:border-blue-400 hover:text-blue-600 text-gray-600"
      >
        + Add Input
      </button>
    </div>
  );
}
