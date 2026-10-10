import test, { beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { authHeaders, clearApiKey, getApiKey, onAuthChange, setApiKey } from '../src/auth.ts';

function fakeStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() { return map.size; },
    clear: () => map.clear(),
    getItem: (k: string) => map.get(k) ?? null,
    key: (i: number) => [...map.keys()][i] ?? null,
    removeItem: (k: string) => { map.delete(k); },
    setItem: (k: string, v: string) => { map.set(k, v); },
  };
}

const g = globalThis as unknown as Record<string, unknown>;

beforeEach(() => {
  g.sessionStorage = fakeStorage();
  // The key must never be written to long-lived storage.
  Object.defineProperty(g, 'localStorage', {
    configurable: true,
    get() { throw new Error('localStorage must not be used for the API key'); },
  });
  clearApiKey();
});

test('there is no key and no header until one is set', () => {
  assert.equal(getApiKey(), null);
  assert.deepEqual(authHeaders(), {});
});

test('a stored key is sent as a bearer token', () => {
  setApiKey('abc123');
  assert.equal(getApiKey(), 'abc123');
  assert.deepEqual(authHeaders(), { Authorization: 'Bearer abc123' });
});

test('the key lives in sessionStorage so it disappears with the tab', () => {
  setApiKey('abc123');
  const stored = Object.values(Object.fromEntries(
    Array.from({ length: (g.sessionStorage as Storage).length }, (_, i) => {
      const k = (g.sessionStorage as Storage).key(i) as string;
      return [k, (g.sessionStorage as Storage).getItem(k)];
    }),
  ));
  assert.deepEqual(stored, ['abc123']);
});

test('clearing removes the key', () => {
  setApiKey('abc123');
  clearApiKey();
  assert.equal(getApiKey(), null);
  assert.deepEqual(authHeaders(), {});
});

test('whitespace is trimmed and a blank key counts as no key', () => {
  setApiKey('  abc123  ');
  assert.equal(getApiKey(), 'abc123');
  setApiKey('   ');
  assert.equal(getApiKey(), null);
});

test('listeners hear about every change until they unsubscribe', () => {
  let calls = 0;
  const unsubscribe = onAuthChange(() => { calls += 1; });
  setApiKey('abc123');
  clearApiKey();
  assert.equal(calls, 2);
  unsubscribe();
  setApiKey('again');
  assert.equal(calls, 2);
});

test('it still works when sessionStorage is unavailable (private mode, blocked storage)', () => {
  Object.defineProperty(g, 'sessionStorage', {
    configurable: true,
    get() { throw new Error('blocked'); },
  });
  setApiKey('memory-only');
  assert.equal(getApiKey(), 'memory-only');
  assert.deepEqual(authHeaders(), { Authorization: 'Bearer memory-only' });
});
