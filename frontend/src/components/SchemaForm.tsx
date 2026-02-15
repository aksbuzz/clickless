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
