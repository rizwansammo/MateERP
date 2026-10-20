'use client';

import { api } from './client';
import { useQuery } from './query';
import type { ApprovalRequest, CompanySummary, Currency, ModulesResponse, Page } from './types';

export const COMPANY_SUMMARY_KEY = '/company/summary/';
export const MODULES_KEY = '/modules/';
export const APPROVAL_INBOX_KEY = '/approvals/requests/?actionable';

export function useCompanySummary() {
  return useQuery(COMPANY_SUMMARY_KEY, () => api.get<CompanySummary>('/company/summary/'));
}

export function useModules() {
  const query = useQuery(MODULES_KEY, () => api.get<ModulesResponse>('/modules/'));
  const states: Record<string, boolean> = {};
  for (const m of query.data?.optional ?? []) states[m.key] = m.enabled;
  return { ...query, states };
}

/** Pending approval requests the current user can decide. */
export function useApprovalInbox() {
  return useQuery(APPROVAL_INBOX_KEY, () =>
    api.get<Page<ApprovalRequest>>('/approvals/requests/', { actionable: 'true', status: 'pending' }),
  );
}

export function useCurrencies() {
  return useQuery('/reference/currencies/', () => api.get<Currency[]>('/reference/currencies/'));
}

export function useTimeZones() {
  return useQuery('/reference/timezones/', () => api.get<{ name: string }[]>('/reference/timezones/'));
}
