import { ApiError, apiRequest } from '@/lib/api/client';
import { fetchHealth } from '@/lib/api/health';

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(typeof body === 'string' ? body : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json', ...headers },
    }),
  );
}

const report = {
  status: 'ok',
  service: 'mateerp-backend',
  version: '0.1.0',
  environment: 'test',
  time: '2026-10-20T10:00:00+06:00',
  checks: { database: { status: 'ok', latency_ms: 1.5 } },
};

describe('apiRequest', () => {
  it('requests same-origin versioned paths and returns JSON', async () => {
    const fetchMock = respond(200, { ok: true });

    await expect(apiRequest('/thing/')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/thing/',
      expect.objectContaining({ method: 'GET', credentials: 'same-origin' }),
    );
  });

  it('turns the standard error envelope into an ApiError', async () => {
    respond(400, {
      error: {
        code: 'validation_error',
        message: 'The request contains invalid data.',
        details: { amount: ['Invalid'] },
        request_id: 'req-12345678',
      },
    });

    const error = await apiRequest('/x/').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      kind: 'http',
      status: 400,
      code: 'validation_error',
      message: 'The request contains invalid data.',
      details: { amount: ['Invalid'] },
      requestId: 'req-12345678',
    });
  });

  it('keeps non-envelope error bodies for the caller', async () => {
    respond(502, { upstream: 'down' }, { 'X-Request-ID': 'abc12345' });

    const error = await apiRequest('/x/').catch((e: unknown) => e);
    expect(error).toMatchObject({ code: 'http_502', status: 502, requestId: 'abc12345', body: { upstream: 'down' } });
  });

  it('reports network failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(apiRequest('/x/')).rejects.toMatchObject({ kind: 'network' });
  });

  it('reports unreadable responses', async () => {
    respond(200, '<html>proxy error</html>');

    await expect(apiRequest('/x/')).rejects.toMatchObject({ kind: 'invalid_response' });
  });
});

describe('fetchHealth', () => {
  it('returns the report when healthy', async () => {
    respond(200, report);
    await expect(fetchHealth()).resolves.toEqual(report);
  });

  it('returns the report on 503 so a degraded state can be shown', async () => {
    const degraded = { ...report, status: 'unavailable', checks: { database: { status: 'unavailable', latency_ms: null } } };
    respond(503, degraded);
    await expect(fetchHealth()).resolves.toEqual(degraded);
  });
});
