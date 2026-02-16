import type { ConfigSchema, SchemaProperty } from '../types';

interface SchemaFormProps {
  schema: ConfigSchema;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
  readOnly?: boolean;
}

export function SchemaForm({ schema, values, onChange, readOnly = false }: SchemaFormProps) {
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  const entries = Object.entries(properties);

  if (entries.length === 0) {
    return <p className="text-sm text-gray-400 italic">No configuration required.</p>;
  }

  function handleChange(key: string, value: unknown) {
    onChange({ ...values, [key]: value });
  }

  return (
    <div className="space-y-4">
      {entries.map(([key, prop]) => (
        <SchemaField
          key={key}
          name={key}
          prop={prop}
          value={values[key]}
          required={required.has(key)}
          readOnly={readOnly}
          onChange={(v) => handleChange(key, v)}
        />
      ))}
    </div>
  );
}

interface SchemaFieldProps {
  name: string;
  prop: SchemaProperty;
  value: unknown;
  required: boolean;
  readOnly: boolean;
  onChange: (value: unknown) => void;
}

function SchemaField({ name, prop, value, required, readOnly, onChange }: SchemaFieldProps) {
  const label = prop.title ?? name;
  const isLongText = prop.description &&
    /code|body|query|message|text|description/i.test(prop.description);
  const supportsTemplates = prop.description?.includes('{{');

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
        {supportsTemplates && (
          <span className="ml-2 text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
            templates
          </span>
        )}
      </label>

      {prop.enum ? (
        <select
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          disabled={readOnly}
          className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm disabled:bg-gray-50"
        >
          <option value="">Select...</option>
          {prop.enum.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      ) : prop.type === 'integer' || prop.type === 'number' ? (
        <input
          type="number"
          value={(value as number) ?? ''}
          onChange={(e) => onChange(e.target.value ? Number(e.target.value) : undefined)}
          min={prop.minimum}
          max={prop.maximum}
          disabled={readOnly}
          className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm disabled:bg-gray-50"
        />
      ) : prop.type === 'object' ? (
        <ObjectEditor
          value={(value as Record<string, unknown>) ?? {}}
          onChange={onChange}
          disabled={readOnly}
        />
      ) : prop.type === 'array' ? (
        <ArrayEditor
          value={(value as unknown[]) ?? []}
          onChange={onChange}
          disabled={readOnly}
          itemType={prop.items?.type}
        />
      ) : isLongText ? (
        <textarea
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          disabled={readOnly}
          rows={4}
          className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm font-mono disabled:bg-gray-50 resize-y"
        />
      ) : (
        <input
          type="text"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          disabled={readOnly}
          className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm disabled:bg-gray-50"
        />
      )}

      {prop.description && (
        <p className="text-xs text-gray-500 mt-1">{prop.description}</p>
      )}
    </div>
  );
}

function ObjectEditor({
  value,
  onChange,
  disabled,
}: {
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  disabled: boolean;
}) {
  const entries = Object.entries(value);

  function handleAddField() {
    onChange({ ...value, '': '' });
  }

  function handleRemoveField(key: string) {
    const newValue = { ...value };
    delete newValue[key];
    onChange(newValue);
  }

  function handleKeyChange(oldKey: string, newKey: string) {
    const newValue: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) {
      newValue[k === oldKey ? newKey : k] = v;
    }
    onChange(newValue);
  }

  function handleValueChange(key: string, newVal: string) {
    onChange({ ...value, [key]: newVal });
  }

  return (
    <div className="space-y-2">
      {entries.map(([key, val]) => (
        <div key={key} className="flex gap-2">
          <input
            type="text"
            value={key}
            onChange={(e) => handleKeyChange(key, e.target.value)}
            placeholder="Key"
            disabled={disabled}
            className="flex-1 border border-gray-300 rounded px-3 py-1.5 text-sm disabled:bg-gray-50"
          />
          <input
            type="text"
            value={String(val ?? '')}
            onChange={(e) => handleValueChange(key, e.target.value)}
            placeholder="Value"
            disabled={disabled}
            className="flex-1 border border-gray-300 rounded px-3 py-1.5 text-sm disabled:bg-gray-50"
          />
          <button
            type="button"
            onClick={() => handleRemoveField(key)}
            disabled={disabled}
            className="px-2 py-1.5 text-sm text-red-600 hover:text-red-700 disabled:text-gray-400"
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={handleAddField}
        disabled={disabled}
        className="text-sm text-blue-600 hover:text-blue-700 disabled:text-gray-400"
      >
        + Add Field
      </button>
    </div>
  );
}

function ArrayEditor({
  value,
  onChange,
  disabled,
  itemType,
}: {
  value: unknown[];
  onChange: (value: unknown[]) => void;
  disabled: boolean;
  itemType?: string;
}) {
  function handleAddItem() {
    onChange([...value, '']);
  }

  function handleRemoveItem(index: number) {
    onChange(value.filter((_, i) => i !== index));
  }

  function handleItemChange(index: number, newVal: unknown) {
    const newValue = [...value];
    newValue[index] = newVal;
    onChange(newValue);
  }

  return (
    <div className="space-y-2">
      {value.map((item, index) => (
        <div key={index} className="flex gap-2">
          <input
            type={itemType === 'number' || itemType === 'integer' ? 'number' : 'text'}
            value={String(item ?? '')}
            onChange={(e) =>
              handleItemChange(
                index,
                itemType === 'number' || itemType === 'integer'
                  ? e.target.value ? Number(e.target.value) : ''
                  : e.target.value
              )
            }
            placeholder={`Item ${index + 1}`}
            disabled={disabled}
            className="flex-1 border border-gray-300 rounded px-3 py-1.5 text-sm disabled:bg-gray-50"
          />
          <button
            type="button"
            onClick={() => handleRemoveItem(index)}
            disabled={disabled}
            className="px-2 py-1.5 text-sm text-red-600 hover:text-red-700 disabled:text-gray-400"
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={handleAddItem}
        disabled={disabled}
        className="text-sm text-blue-600 hover:text-blue-700 disabled:text-gray-400"
      >
        + Add Item
      </button>
    </div>
  );
}
