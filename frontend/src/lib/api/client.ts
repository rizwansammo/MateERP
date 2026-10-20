/*
 * Typed API client. All requests go to the same origin under /api/v1;
 * Next.js proxies them to Django (see next.config.ts).
 *
 * Session cookies are HttpOnly and never touched here. State-changing
 * requests carry Django's CSRF token (read from the mateerp_csrftoken
 * cookie) in the X-CSRFToken header.
 */

export const API_BASE = '/api/v1';
const DEFAULT_TIMEOUT_MS = 15_000;
const CSRF_COOKIE = 'mateerp_csrftoken';
const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** Fired when an authenticated request reports that the session has ended. */
export const SESSION_EXPIRED_EVENT = 'mateerp:session-expired';

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

  /** Field-level validation messages, keyed by field name. */
  fieldErrors(): Record<string, string> {
    if (typeof this.details !== 'object' || this.details === null) return {};
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(this.details as Record<string, unknown>)) {
      if (Array.isArray(value) && value.length) out[key] = String(value[0]);
      else if (typeof value === 'string') out[key] = value;
      else if (value && typeof value === 'object') {
        // Nested (e.g. numbering.invoice): flatten one level.
        for (const [inner, msg] of Object.entries(value as Record<string, unknown>)) {
          out[`${key}.${inner}`] = Array.isArray(msg) ? String(msg[0]) : String(msg);
        }
      }
    }
    return out;
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

export function readCsrfCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.split('; ').find((c) => c.startsWith(`${CSRF_COOKIE}=`));
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE.length + 1)) : null;
}

/** Ensure the CSRF cookie exists (Django issues it from /auth/csrf/). */
export async function ensureCsrf(force = false): Promise<string | null> {
  if (!force) {
    const existing = readCsrfCookie();
    if (existing) return existing;
  }
  await fetch(`${API_BASE}/auth/csrf/`, { credentials: 'same-origin', cache: 'no-store' });
  return readCsrfCookie();
}

export type RequestBody = Record<string, unknown> | unknown[] | FormData;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: RequestBody;
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Do not broadcast a session-expired event on 401 (used by auth endpoints). */
  quiet401?: boolean;
}

function withQuery(path: string, query: RequestOptions['query']): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}${path.includes('?') ? '&' : '?'}${qs}` : path;
}

async function send(path: string, options: RequestOptions, csrf: string | null): Promise<Response> {
  const { method = 'GET', body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const timeout = AbortSignal.timeout(timeoutMs);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  if (csrf) headers['X-CSRFToken'] = csrf;

  try {
    return await fetch(`${API_BASE}${withQuery(path, options.query)}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
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
}

async function parse<T>(response: Response, options: RequestOptions): Promise<T> {
  const requestId = response.headers.get('X-Request-ID');
  let payload: unknown = null;
  const text = response.status === 204 ? '' : await response.text();
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
    if (response.status === 401 && !options.quiet401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
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

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  const unsafe = UNSAFE.has(method);
  const csrf = unsafe ? await ensureCsrf() : null;
  try {
    return await parse<T>(await send(path, options, csrf), options);
  } catch (error) {
    // A rotated or missing token (e.g. after sign-in elsewhere): refresh once and retry.
    if (unsafe && error instanceof ApiError && error.code === 'csrf_failed') {
      const fresh = await ensureCsrf(true);
      return parse<T>(await send(path, options, fresh), options);
    }
    throw error;
  }
}

export const api = {
  get: <T>(path: string, query?: RequestOptions['query'], signal?: AbortSignal) =>
    apiRequest<T>(path, { query, signal }),
  post: <T>(path: string, body?: RequestBody) => apiRequest<T>(path, { method: 'POST', body }),
  put: <T>(path: string, body?: RequestBody) => apiRequest<T>(path, { method: 'PUT', body }),
  patch: <T>(path: string, body?: RequestBody) => apiRequest<T>(path, { method: 'PATCH', body }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: 'DELETE' }),
};

/** Turn any thrown value into a user-facing message. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong.';
}
