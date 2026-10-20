'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Wordmark } from '@/components/brand/Wordmark';
import { Badge } from '@/components/ui/Badge';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Segmented } from '@/components/ui/Choice';
import { Field } from '@/components/ui/Field';
import { InfoPanel, InfoPanels } from '@/components/ui/InfoPanel';
import { Input, Select } from '@/components/ui/Input';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader } from '@/components/ui/Panel';
import { toast } from '@/components/ui/Toast';
import { api } from '@/lib/api/client';
import { useCompanySummary } from '@/lib/api/hooks';
import { useQuery } from '@/lib/api/query';
import type { CurrentUser } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDateTime } from '@/lib/format';
import { useFormState } from '@/lib/forms';
import { PHASES } from '@/lib/navigation';
import { setSidebarMode, setTheme, useSidebarMode, useTheme } from '@/lib/preferences';

import { type HealthReport, fetchHealth } from '@/lib/api/health';

// --- Application preferences ---------------------------------------------------------

const LANDING = [
  ['/dashboard', 'Dashboard'],
  ['/settings/company', 'Company profile'],
  ['/settings/users', 'Users & roles'],
  ['/settings/branding', 'Invoice & receipt branding'],
] as const;

export function PreferencesPage() {
  const { user, savePreferences } = useAuth();
  const { theme } = useTheme();
  const { mode } = useSidebarMode();
  const rows = user.preferences.rows_per_page ?? 25;
  const landing = user.preferences.landing_page ?? '/dashboard';

  const save = (prefs: Parameters<typeof savePreferences>[0], message: string) => {
    savePreferences(prefs);
    toast(message);
  };

  return (
    <PageContainer>
      <PageHeader eyebrow="Settings" title="Application preferences" description="Personal interface preferences. They are saved to your account and follow you to every device you sign in on." />
      <Panel>
        <PanelHeader title="Appearance" />
        <PanelBody className="flex flex-col gap-4">
          <Field label="Theme" htmlFor="pref-theme">
            <Segmented label="Theme" value={theme} onChange={(v) => { setTheme(v); save({ theme: v }, `${v === 'dark' ? 'Dark' : 'Light'} theme saved`); }} options={[{ value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]} />
          </Field>
          <Field label="Sidebar" htmlFor="pref-sidebar">
            <Segmented label="Sidebar" value={mode} onChange={(v) => { setSidebarMode(v); save({ sidebar: v }, 'Sidebar preference saved'); }} options={[{ value: 'full', label: 'Expanded' }, { value: 'compact', label: 'Compact' }]} />
          </Field>
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader title="Tables & navigation" />
        <PanelBody className="flex flex-col gap-4">
          <Field label="Rows per table page" htmlFor="pref-rows">
            <Segmented label="Rows per table page" value={String(rows)} onChange={(v) => save({ rows_per_page: Number(v) as 10 | 25 | 50 }, `Tables now show ${v} rows`)} options={[{ value: '10', label: '10' }, { value: '25', label: '25' }, { value: '50', label: '50' }]} />
          </Field>
          <Field label="Page after sign-in" htmlFor="pref-landing">
            <Select id="pref-landing" className="max-w-[320px]" value={landing} onChange={(e) => save({ landing_page: e.target.value }, 'Landing page saved')}>
              {LANDING.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </Select>
          </Field>
        </PanelBody>
      </Panel>
    </PageContainer>
  );
}

// --- About -----------------------------------------------------------------------------

export function AboutPage() {
  const health = useQuery('/health/', () => fetchHealth());
  const company = useCompanySummary();
  const h: HealthReport | undefined = health.data;
  return (
    <PageContainer>
      <PageHeader eyebrow="Settings" title="About MateERP" description="MateERP — a NetaMate product. Enterprise resource planning for a single company per installation." />
      <div className="flex flex-col items-start gap-3 border border-bd bg-splash-bg px-8 py-10 text-splash-fg">
        <div className="text-[52px] max-sm:text-[36px]"><Wordmark /></div>
        <div className="text-[11px] uppercase tracking-[.38em] text-sb-tx2">Enterprise Resource Planning</div>
      </div>
      <InfoPanels>
        <InfoPanel title="Product" rows={[
          { label: 'Product', value: 'MateERP' },
          { label: 'Version', value: h ? `${h.version} · ${h.environment}` : '—' },
          { label: 'Ecosystem', value: 'NetaMate (MateCRM, MateHR — separate products)' },
          { label: 'Licensed to', value: company.data?.display_name ?? 'Company not configured' },
          { label: 'Model', value: 'Single company per installation' },
        ]} />
        <InfoPanel title="Delivered" rows={[
          { label: 'Phase 1', value: PHASES[1]! },
          { label: 'Phase 2', value: PHASES[2]! },
          { label: 'Phase 3', value: PHASES[3]! },
        ]} />
        <InfoPanel title="Roadmap" rows={[4, 5, 6, 7].map((p) => ({ label: `Phase ${p}`, value: PHASES[p]!, tone: 'muted' as const }))} />
      </InfoPanels>
    </PageContainer>
  );
}

// --- Planned settings sections --------------------------------------------------------

export function PlannedSettingsPage({ title, phase, description }: { title: string; phase: number; description: string }) {
  return (
    <PageContainer>
      <PageHeader eyebrow="Settings" title={title} description={description} actions={<Badge tone="info">{`Planned · Phase ${phase}`}</Badge>} />
      <Panel>
        <PanelHeader title="Delivery status" subtitle={`Phase ${phase} · ${PHASES[phase]}`} />
        <PanelBody className="text-[13px] leading-[1.55] text-tx2">
          <p className="m-0" data-testid="planned-notice">
            <strong className="font-semibold text-tx">{title}</strong> is scheduled for Phase {phase} and is not implemented yet. Nothing on this page
            can be configured until it is delivered.
          </p>
        </PanelBody>
      </Panel>
    </PageContainer>
  );
}

// --- My profile -------------------------------------------------------------------------

export function ProfilePage() {
  const { user, setUser } = useAuth();
  const form = useFormState({ first_name: user.first_name, last_name: user.last_name, email: user.email });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!/^\S+@\S+\.\S+$/.test(form.values.email)) {
      form.setErrors({ email: 'Enter a valid email address.' });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = await api.patch<CurrentUser>('/auth/me/', form.values);
      setUser(saved);
      form.reset({ first_name: saved.first_name, last_name: saved.last_name, email: saved.email });
      toast('Profile saved');
    } catch (err) {
      setError(form.applyError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Account"
        title="My profile"
        description="Your name and contact email. Your role is managed by an administrator."
        actions={
          <Link href="/account/password" className="inline-flex h-[34px] items-center gap-1.5 border border-bd2 bg-sf px-3.5 text-[12.5px] font-medium text-tx hover:bg-sf3 hover:text-tx hover:no-underline">
            Change password
          </Link>
        }
      />
      {error && <Banner tone="err">{error}</Banner>}
      <InfoPanels>
        <Panel>
          <PanelHeader title="Personal details" />
          <PanelBody className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="First name" htmlFor="me-first" error={form.errors.first_name}>
                <Input id="me-first" maxLength={150} value={form.values.first_name} onChange={(e) => form.set('first_name', e.target.value)} />
              </Field>
              <Field label="Last name" htmlFor="me-last" error={form.errors.last_name}>
                <Input id="me-last" maxLength={150} value={form.values.last_name} onChange={(e) => form.set('last_name', e.target.value)} />
              </Field>
            </div>
            <Field label="Contact email" htmlFor="me-email" error={form.errors.email}>
              <Input id="me-email" type="email" maxLength={254} value={form.values.email} invalid={Boolean(form.errors.email)} onChange={(e) => form.set('email', e.target.value.trim())} />
            </Field>
            <div className="flex justify-end">
              <Button variant="primary" disabled={!form.dirty || busy} onClick={() => void save()}>{busy ? 'Saving…' : 'Save profile'}</Button>
            </div>
          </PanelBody>
        </Panel>
        <InfoPanel title="Access" rows={[
          { label: 'Username', value: user.username },
          { label: 'Role', value: user.role?.name ?? 'No role' },
          { label: 'Permissions', value: `${user.permissions.length} granted` },
          { label: 'Last sign-in', value: formatDateTime(user.last_login) },
        ]} />
      </InfoPanels>
    </PageContainer>
  );
}
