import { ApiError, apiRequest } from '@/lib/api/client';
import { fetchHealth } from '@/lib/api/health';
import { invalidate, setQueryData } from '@/lib/api/query';

import { mockApi } from './helpers';

const report = {
  status: 'ok',
  service: 'mateerp-backend',
  version: '0.2.0',
  environment: 'test',
  time: '2026-10-20T10:00:00+06:00',
  checks: { database: { status: 'ok', latency_ms: 1.5 } },
};

describe('apiRequest', () => {
  it('requests same-origin versioned paths without CSRF for reads', async () => {
    const calls = mockApi({ '/thing/': { ok: true } });
    await expect(apiRequest('/thing/', { query: { q: 'a b', empty: '' } })).resolves.toEqual({ ok: true });
    expect(calls).toHaveLength(1);
    expect(calls[0]!.path).toBe('/thing/?q=a+b');
    expect(calls[0]!.headers['X-CSRFToken']).toBeUndefined();
  });

  it('initialises CSRF once and sends the token on unsafe requests', async () => {
    const calls = mockApi({ 'POST /thing/': { ok: true } });
    await apiRequest('/thing/', { method: 'POST', body: { a: 1 } });
    await apiRequest('/thing/', { method: 'POST', body: { a: 2 } });
    expect(calls.filter((c) => c.path === '/auth/csrf/')).toHaveLength(1);
    expect(calls.filter((c) => c.path === '/thing/').every((c) => c.headers['X-CSRFToken'] === 'test-token')).toBe(true);
  });

  it('refreshes the token and retries once after csrf_failed', async () => {
    document.cookie = 'mateerp_csrftoken=stale';
    let attempts = 0;
    const calls = mockApi({
      'POST /thing/': () => {
        attempts += 1;
        return attempts === 1
          ? [403, { error: { code: 'csrf_failed', message: 'Security check failed.', details: null, request_id: null } }]
          : { ok: true };
      },
    });
    await expect(apiRequest('/thing/', { method: 'POST' })).resolves.toEqual({ ok: true });
    expect(attempts).toBe(2);
    expect(calls.map((c) => c.path)).toEqual(['/thing/', '/auth/csrf/', '/thing/']);
  });

  it('sends FormData without a JSON content type', async () => {
    const calls = mockApi({ 'POST /upload/': { ok: true } });
    const form = new FormData();
    form.append('file', new Blob(['x'], { type: 'image/png' }), 'a.png');
    await apiRequest('/upload/', { method: 'POST', body: form });
    expect(calls.at(-1)!.headers['Content-Type']).toBeUndefined();
  });

  it('turns the standard error envelope into an ApiError with field errors', async () => {
    mockApi({
      'POST /x/': [400, { error: { code: 'validation_error', message: 'The request contains invalid data.', details: { amount: ['Invalid'], numbering: { invoice: 'Bad' } }, request_id: 'req-1' } }],
    });
    const error = (await apiRequest('/x/', { method: 'POST' }).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: 'http', status: 400, code: 'validation_error', requestId: 'req-1' });
    expect(error.fieldErrors()).toEqual({ amount: 'Invalid', 'numbering.invoice': 'Bad' });
  });

  it('reports network failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(apiRequest('/x/')).rejects.toMatchObject({ kind: 'network' });
  });
});

describe('fetchHealth', () => {
  it('returns the report on 503 so a degraded state can be shown', async () => {
    const degraded = { ...report, status: 'unavailable', checks: { database: { status: 'unavailable', latency_ms: null } } };
    mockApi({ '/health/': [503, degraded] });
    await expect(fetchHealth()).resolves.toEqual(degraded);
  });
});

describe('query cache', () => {
  it('invalidate refetches only matching mounted queries', () => {
    setQueryData('/company/', { a: 1 });
    setQueryData('/users/?page=1', { b: 1 });
    expect(() => invalidate('/company/')).not.toThrow();
  });
});
