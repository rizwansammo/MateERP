/*
 * Minimal typed API client. All requests go to the same origin under /api/v1;
 * Next.js proxies them to Django (see next.config.ts).
 */

export const API_BASE = '/api/v1';
const DEFAULT_TIMEOUT_MS = 10_000;

/** Shape of every backend error response (apps/core/exceptions.py). */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: unknown;
    request_id: string | null;
  };
}

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'invalid_response';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;
  /** Parsed body for HTTP errors whose body is not the standard envelope (e.g. 503 health). */
  readonly body: unknown;

  constructor(init: {
    kind: ApiErrorKind;
    message: string;
    status?: number | null;
    code?: string;
    details?: unknown;
    requestId?: string | null;
    body?: unknown;
  }) {
    super(init.message);
    this.name = 'ApiError';
    this.kind = init.kind;
    this.status = init.status ?? null;
    this.code = init.code ?? init.kind;
    this.details = init.details ?? null;
    this.requestId = init.requestId ?? null;
    this.body = init.body ?? null;
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code?: unknown }).code === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  );
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const timeout = AbortSignal.timeout(timeoutMs);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: 'same-origin',
      cache: 'no-store',
      signal: combined,
    });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    if (timeout.aborted) {
      throw new ApiError({ kind: 'timeout', message: 'The server took too long to respond.' });
    }
    throw new ApiError({ kind: 'network', message: 'The server could not be reached.' });
  }

  const requestId = response.headers.get('X-Request-ID');
  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      throw new ApiError({
        kind: 'invalid_response',
        status: response.status,
        message: 'The server returned an unreadable response.',
        requestId,
      });
    }
  }

  if (!response.ok) {
    if (isErrorBody(payload)) {
      throw new ApiError({
        kind: 'http',
        status: response.status,
        code: payload.error.code,
        message: payload.error.message,
        details: payload.error.details,
        requestId: payload.error.request_id ?? requestId,
      });
    }
    throw new ApiError({
      kind: 'http',
      status: response.status,
      code: `http_${response.status}`,
      message: `Request failed with status ${response.status}.`,
      requestId,
      body: payload,
    });
  }

  return payload as T;
}
