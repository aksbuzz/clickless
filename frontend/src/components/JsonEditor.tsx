interface JsonEditorProps {
  value: string;
  onChange: (value: string) => void;
  error?: string | null;
  placeholder?: string;
  rows?: number;
}

export function JsonEditor({ value, onChange, error, placeholder, rows = 8 }: JsonEditorProps) {
  function handleBlur() {
    try {
      const parsed = JSON.parse(value);
      onChange(JSON.stringify(parsed, null, 2));
    } catch {
      // leave as-is if invalid
    }
  }

  return (
    <div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={handleBlur}
        placeholder={placeholder ?? '{\n  "key": "value"\n}'}
        rows={rows}
        className={`w-full font-mono text-sm p-3 border rounded resize-y ${
          error ? 'border-red-400' : 'border-gray-300'
        } focus:outline-none focus:ring-2 focus:ring-blue-500`}
      />
      {error && <p className="text-red-600 text-xs mt-1">{error}</p>}
    </div>
  );
}
