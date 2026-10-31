import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { ApiError, getHealth, hitlStart } from '../src/lib/api.ts';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

test('health calls carry a timeout signal and read NVIDIA configuration', async () => {
  globalThis.fetch = async (_url, init) => {
    assert.ok(init?.signal instanceof AbortSignal);
    return new Response(JSON.stringify({provider:'nvidia', nvidia_key:true}), {status:200});
  };
  assert.equal((await getHealth()).nvidia_key, true);
});

test('rate limits remain distinct and provider messages are shown', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({detail:'Wait before retrying'}), {status:429});
  await assert.rejects(hitlStart('AI', false), (error: unknown) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 429);
    return true;
  });
});

test('non-JSON success responses are rejected safely', async () => {
  globalThis.fetch = async () => new Response('<html>Proxy error</html>', {status:200});
  await assert.rejects(getHealth(), ApiError);
});

test('lost response does not claim the server job was cancelled', async () => {
  globalThis.fetch = async () => { throw new DOMException('Aborted', 'TimeoutError'); };
  await assert.rejects(hitlStart('AI', false), (error: unknown) => {
    assert.ok(error instanceof ApiError);
    assert.match(error.detail, /may still be running/);
    return true;
  });
});
