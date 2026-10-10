// The shared API key the backend requires on every request. It is kept in sessionStorage, so it disappears
// when the tab is closed, and is never written to localStorage. If sessionStorage is blocked (private mode,
// strict browser settings) it is held in memory for the current page load instead.

const STORAGE_KEY = 'workflow-engine.api-key';

let memoryKey: string | null = null;
const listeners = new Set<() => void>();

function sessionStore(): Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

function emit(): void {
  listeners.forEach((listener) => listener());
}

export function getApiKey(): string | null {
  const store = sessionStore();
  if (store) {
    try {
      return store.getItem(STORAGE_KEY);
    } catch {
      // fall through to the in-memory copy
    }
  }
  return memoryKey;
}

export function setApiKey(key: string): void {
  const trimmed = key.trim();
  if (!trimmed) {
    clearApiKey();
    return;
  }
  let stored = false;
  const store = sessionStore();
  if (store) {
    try {
      store.setItem(STORAGE_KEY, trimmed);
      stored = true;
    } catch {
      // storage refused the write; keep the key in memory
    }
  }
  memoryKey = stored ? null : trimmed;
  emit();
}

export function clearApiKey(): void {
  try {
    sessionStore()?.removeItem(STORAGE_KEY);
  } catch {
    // nothing stored that we could remove
  }
  memoryKey = null;
  emit();
}

export function authHeaders(): Record<string, string> {
  const key = getApiKey();
  return key ? { Authorization: `Bearer ${key}` } : {};
}

/** The server rejected the key: forget it so the UI asks again. */
export function handleUnauthorized(): void {
  clearApiKey();
}

/** Subscribe to key changes (set, clear, rejected). Returns an unsubscribe function. */
export function onAuthChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
