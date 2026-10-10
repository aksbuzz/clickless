import { useState, useSyncExternalStore, type FormEvent, type ReactNode } from 'react';
import { api } from '../api';
import { getApiKey, onAuthChange, setApiKey } from '../auth';

/** Shows the app only once an API key the server accepts has been entered; a rejected key brings the form back. */
export function ApiKeyGate({ children }: { children: ReactNode }) {
  const key = useSyncExternalStore(onAuthChange, getApiKey, () => null);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  if (key) return <>{children}</>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setChecking(true);
    setError(null);
    try {
      if (await api.checkApiKey(draft)) {
        setApiKey(draft);
      } else {
        setError('That key was not accepted.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reach the API.');
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-white border border-gray-200 rounded p-6 space-y-4">
        <h1 className="text-lg font-semibold">Workflow Engine</h1>
        <p className="text-sm text-gray-600">Enter the API key to continue. It is kept for this browser tab only.</p>
        <label className="block text-sm font-medium" htmlFor="api-key">API key</label>
        <input
          id="api-key"
          type="password"
          autoComplete="off"
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
        />
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={checking || !draft.trim()}
          className="w-full bg-gray-900 text-white rounded px-3 py-2 text-sm disabled:opacity-50"
        >
          {checking ? 'Checking...' : 'Continue'}
        </button>
      </form>
    </div>
  );
}
