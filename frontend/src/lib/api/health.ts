import { ApiError, apiRequest } from './client';

export type CheckStatus = 'ok' | 'unavailable';

export interface HealthReport {
  status: CheckStatus;
  service: string;
  version: string;
  environment: string;
  time: string;
  checks: {
    database: { status: CheckStatus; latency_ms: number | null };
  };
}

function isHealthReport(value: unknown): value is HealthReport {
  return (
    typeof value === 'object' &&
    value !== null &&
    'status' in value &&
    'checks' in value &&
    'service' in value
  );
}

/**
 * Fetch backend health. A 503 still carries a full report (the backend is up
 * but a dependency is not), so it is returned rather than thrown.
 */
export async function fetchHealth(signal?: AbortSignal): Promise<HealthReport> {
  try {
    return await apiRequest<HealthReport>('/health/', { signal });
  } catch (error) {
    if (error instanceof ApiError && error.status === 503 && isHealthReport(error.body)) {
      return error.body;
    }
    throw error;
  }
}
