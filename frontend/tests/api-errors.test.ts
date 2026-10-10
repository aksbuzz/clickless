import test, { beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { api } from '../src/api.ts';
import { clearApiKey, setApiKey } from '../src/auth.ts';

const g = globalThis as unknown as Record<string, unknown>;

function stubFetch(status: number, body: unknown, statusText = 'Bad Request') {
  g.fetch = async () =>
    new Response(JSON.stringify(body), { status, statusText, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  const map = new Map<string, string>();
  g.sessionStorage = {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => { map.set(k, v); },
    removeItem: (k: string) => { map.delete(k); },
  };
  clearApiKey();
  setApiKey('k');
});

test('a create that fails validation shows the messages the API returned', async () => {
  stubFetch(400, { validation_errors: ['Personal Access Token is required', "Unknown field 'password'"] });
  await assert.rejects(
    api.createConnection('github', 'main', {}),
    { message: "Personal Access Token is required; Unknown field 'password'" },
  );
});

test('an update that fails validation shows the messages too', async () => {
  stubFetch(400, { validation_errors: ['API Key is required'] });
  await assert.rejects(api.updateConnection('c', 'n', {}), { message: 'API Key is required' });
});

test('a plain detail message is still shown', async () => {
  stubFetch(409, { detail: "Connection name 'main' already exists for connector 'github'" }, 'Conflict');
  await assert.rejects(api.createConnection('github', 'main', { token: 'x' }), { message: "Connection name 'main' already exists for connector 'github'" });
});

test('FastAPI-style detail lists are joined', async () => {
  stubFetch(422, { detail: ['first', 'second'] }, 'Unprocessable Entity');
  await assert.rejects(api.createConnection('github', 'main', {}), { message: 'first; second' });
});

test('without a readable body the status line is shown', async () => {
  g.fetch = async () => new Response('<html>', { status: 502, statusText: 'Bad Gateway' });
  await assert.rejects(api.createConnection('github', 'main', {}), { message: '502 Bad Gateway' });
});

test('a failed read shows the message the API returned', async () => {
  stubFetch(404, { detail: 'Connection not found' }, 'Not Found');
  await assert.rejects(api.getConnection('missing'), { message: 'Connection not found' });
});

test('a failed read without a readable body shows the status line', async () => {
  g.fetch = async () => new Response('oops', { status: 500, statusText: 'Internal Server Error' });
  await assert.rejects(api.getWorkflows(), { message: '500 Internal Server Error' });
});
