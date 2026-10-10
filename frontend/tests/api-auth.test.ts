import test, { beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { api, UnauthorizedError } from '../src/api.ts';
import { clearApiKey, getApiKey, onAuthChange, setApiKey } from '../src/auth.ts';

type Call = { url: string; init?: RequestInit };
const g = globalThis as unknown as Record<string, unknown>;
let calls: Call[] = [];

function stubFetch(status: number, body: unknown = {}, statusText = '') {
  calls = [];
  g.fetch = async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify(body), { status, statusText, headers: { 'Content-Type': 'application/json' } });
  };
}

const header = (call: Call, name: string) => new Headers(call.init?.headers).get(name);

beforeEach(() => {
  const map = new Map<string, string>();
  g.sessionStorage = {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => { map.set(k, v); },
    removeItem: (k: string) => { map.delete(k); },
  };
  clearApiKey();
});

test('requests carry the API key as a bearer token', async () => {
  setApiKey('k-123');
  stubFetch(200, []);
  await api.getWorkflows();
  assert.equal(calls[0].url, '/api/workflows');
  assert.equal(header(calls[0], 'authorization'), 'Bearer k-123');
});

test('POST, PUT and DELETE carry the key too, and POST keeps its content type', async () => {
  setApiKey('k-123');
  stubFetch(200, { message: 'ok', instance_id: 'i' });
  await api.runWorkflow('w', { a: 1 });
  await api.updateConnection('c', 'n', {});
  await api.deleteConnection('c');
  assert.deepEqual(calls.map((c) => header(c, 'authorization')), ['Bearer k-123', 'Bearer k-123', 'Bearer k-123']);
  assert.equal(header(calls[0], 'content-type'), 'application/json');
});

test('without a key no Authorization header is sent', async () => {
  stubFetch(200, []);
  await api.getWorkflows();
  assert.equal(header(calls[0], 'authorization'), null);
});

test('a 401 clears the key, tells listeners, and rejects with UnauthorizedError', async () => {
  setApiKey('wrong');
  let notified = 0;
  onAuthChange(() => { notified += 1; });
  stubFetch(401, { detail: 'Invalid or missing API key' });
  await assert.rejects(() => api.getWorkflows(), (err: unknown) => err instanceof UnauthorizedError);
  assert.equal(getApiKey(), null);
  assert.ok(notified >= 1);
});

test('a 401 on a write is handled the same way', async () => {
  setApiKey('wrong');
  stubFetch(401, { detail: 'nope' });
  await assert.rejects(() => api.runWorkflow('w', {}), (err: unknown) => err instanceof UnauthorizedError);
  assert.equal(getApiKey(), null);
});

test('other errors are unchanged and keep the key', async () => {
  setApiKey('k-123');
  stubFetch(404, { detail: 'Workflow not found' }, 'Not Found');
  await assert.rejects(() => api.getWorkflow('x'), /404 Not Found/);
  stubFetch(409, { detail: 'Workflow name already exists' });
  await assert.rejects(() => api.createWorkflow('n', {}), /Workflow name already exists/);
  assert.equal(getApiKey(), 'k-123');
});

test('checkApiKey verifies a candidate key without storing it', async () => {
  stubFetch(200, []);
  assert.equal(await api.checkApiKey('candidate'), true);
  assert.equal(header(calls[0], 'authorization'), 'Bearer candidate');
  assert.equal(getApiKey(), null);
});

test('checkApiKey reports a rejected key as false and leaves the stored key alone', async () => {
  setApiKey('stored');
  stubFetch(401, { detail: 'Invalid or missing API key' });
  assert.equal(await api.checkApiKey('wrong'), false);
  assert.equal(getApiKey(), 'stored');
});

test('checkApiKey surfaces the server message for any other failure', async () => {
  stubFetch(503, { detail: 'API key is not configured' });
  await assert.rejects(() => api.checkApiKey('x'), /API key is not configured/);
});
