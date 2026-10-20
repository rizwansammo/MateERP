'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { type ReactNode, useState } from 'react';

import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox, Segmented } from '@/components/ui/Choice';
import { Field } from '@/components/ui/Field';
import { Icon } from '@/components/ui/Icon';
import { AmountInput, Input, Select, Textarea } from '@/components/ui/Input';
import { PageContainer } from '@/components/ui/PageHeader';
import { toast } from '@/components/ui/Toast';
import { api, ApiError, errorMessage } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useUnsavedGuard } from '@/lib/forms';
import { formatDate } from '@/lib/format';

import { useConfig } from '@/features/accounting/shared';
import { type EditLine, LinesEditor, Totals, blankLine, toEditLines, toPayload, useCalculation } from '@/features/commerce/lines';
import { refreshCommerce, today, trimDecimal, useApi, useMoney } from '@/features/commerce/shared';
import type { Customer, Invoice, Project, SalesOrder } from '@/features/commerce/types';

import { CustomerDrawer } from './Customers';
import { InvoicePaper, draftView, useDocFormat, useDocumentBranding } from './preview';

type Source = 'standard' | 'project' | 'milestone' | 'order';

function addDays(date: string, days: number) {
  const d = new Date(`${date}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toLocaleDateString('en-CA');
}

function Section({ n, title, aside, children }: { n: string; title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="border border-bd bg-sf">
      <header className="flex items-center justify-between gap-2 border-b border-bd px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] font-semibold text-ac">{n}</span>
          <span className="text-[13px] font-semibold">{title}</span>
        </div>
        {aside && <span className="text-[11.5px] text-tx3">{aside}</span>}
      </header>
      {children}
    </section>
  );
}

export function InvoiceEditor({ id }: { id?: string }) {
  const existing = useApi<Invoice>(id ? `/billing/invoices/${id}/` : null);
  if (id && !existing.data) return <PageContainer>{existing.error ? <Banner tone="err">{errorMessage(existing.error)}</Banner> : <span className="text-tx3">Loading invoice…</span>}</PageContainer>;
  return <InvoiceEditorForm key={id ?? 'new'} id={id} initial={existing.data} />;
}

function InvoiceEditorForm({ id, initial }: { id?: string; initial?: Invoice }) {
  const router = useRouter();
  const params = useSearchParams();
  const { can } = useAuth();
  const money = useMoney();
  const config = useConfig();
  const [persisted, setPersisted] = useState(initial);
  const existing = { data: persisted };
  const customers = useApi<Page<Customer>>('/sales/customers/?status=active&page_size=100');
  const [customerId, setCustomerId] = useState(initial ? String(initial.customer_id) : params.get('customer') ?? '');
  const [currencyChoice, setCurrency] = useState(initial?.currency ?? '');
  const [issueDate, setIssueDate] = useState(initial?.issue_date ?? today());
  const [dueOverride, setDueDate] = useState(initial?.due_date ?? '');
  const [dueTouched, setDueTouched] = useState(Boolean(initial));
  const [reference, setReference] = useState(initial?.reference ?? '');
  const [notes, setNotes] = useState(initial?.notes ?? '');
  const [inclusive, setInclusive] = useState(initial?.prices_include_tax ?? false);
  const [discountType, setDiscountType] = useState<'percent' | 'fixed'>(initial?.discount_type ?? 'percent');
  const [discountValue, setDiscountValue] = useState(trimDecimal(initial?.discount_value) || '0');
  const [projectId, setProjectId] = useState(initial?.project_id ? String(initial.project_id) : '');
  const [source, setSource] = useState<Source>(initial?.milestone_id ? 'milestone' : initial?.sales_order_id ? 'order' : initial?.project_id ? 'project' : 'standard');
  const [lines, setLines] = useState<EditLine[]>(initial ? toEditLines(initial.lines, 'revenue_account_id') : [blankLine()]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newCustomer, setNewCustomer] = useState(false);
  useUnsavedGuard(dirty && !busy);

  const customer = customers.data?.results.find((c) => String(c.id) === customerId);
  const currency = currencyChoice || customer?.currency || config.data?.base_currency || '';
  const dueDate = dueTouched ? dueOverride : customer ? addDays(issueDate, customer.payment_terms_days) : '';
  const projects = useApi<Page<Project>>(customerId ? `/sales/projects/?customer=${customerId}&page_size=50` : null);
  const orders = useApi<Page<SalesOrder>>(customerId && source === 'order' ? `/sales/orders/?customer=${customerId}&page_size=50` : null);
  const project = projects.data?.results.find((p) => String(p.id) === projectId);
  const financials = useApi<{ milestones: { id: number; invoice: { id: number; number: string | null; status: string } | null }[] }>(
    project && source === 'milestone' ? `/billing/projects/${project.id}/financials/` : null,
  );
  const branding = useDocumentBranding();

  const change = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setDirty(true);
  };
  const calc = useCalculation({ currency, date: issueDate, lines, pricesIncludeTax: inclusive, discountType, discountValue });
  const fmt = useDocFormat(currency || config.data?.base_currency || 'BDT');

  if (id && existing.data && existing.data.number) {
    return (
      <PageContainer>
        <Banner tone="warn">
          {existing.data.number} is issued and locked. Correct it with a credit note. <Link href={`/sales/invoices/${id}`}>Open invoice</Link>
        </Banner>
      </PageContainer>
    );
  }

  const payload = () => ({
    customer_id: Number(customerId),
    currency,
    issue_date: issueDate,
    due_date: dueDate || null,
    reference,
    notes,
    prices_include_tax: inclusive,
    discount_type: discountType,
    discount_value: discountValue || '0',
    project_id: projectId ? Number(projectId) : null,
    lines: toPayload(lines, 'revenue_account_id'),
    ...(existing.data ? { revision: existing.data.revision } : {}),
  });

  const save = async (issue: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const saved = existing.data
        ? await api.patch<Invoice>(`/billing/invoices/${existing.data.id}/`, payload())
        : await api.post<Invoice>('/billing/invoices/', payload());
      setPersisted(saved);
      let message = 'Draft saved';
      if (issue) {
        const issued = await api.post<Invoice>(`/billing/invoices/${saved.id}/issue/`);
        message = issued.number ? `Invoice ${issued.number} issued · PDF ${issued.pdf_status}` : 'Submitted for approval — no invoice issued yet';
      }
      setDirty(false);
      refreshCommerce();
      toast(message);
      router.push(`/sales/invoices/${saved.id}`);
    } catch (e) {
      setError(e instanceof ApiError && e.code === 'validation_error' ? Object.entries(e.fieldErrors()).map(([k, v]) => `${k}: ${v}`).join(' · ') || e.message : errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const fromSource = async (body: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    try {
      const created = await api.post<Invoice>('/billing/invoices/from-source/', { issue_date: issueDate, ...body });
      refreshCommerce();
      toast('Draft invoice created — review and issue');
      router.push(`/sales/invoices/${created.id}/edit`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const billedMilestones = new Map((financials.data?.milestones ?? []).map((m) => [m.id, m.invoice]));
  const view = draftView(
    {
      issue_date: issueDate,
      due_date: dueDate || issueDate,
      currency: currency || fmt.currency,
      reference,
      notes,
      prices_include_tax: inclusive,
      customer,
      project: project ? { reference: project.reference, name: project.name } : null,
      descriptions: toPayload(lines, 'revenue_account_id').map((l) => l.description),
      discountTypes: lines.map((l) => l.discount_type),
      discountValues: lines.map((l) => l.discount_value),
    },
    calc.result,
    fmt,
    'VAT',
  );


  return (
    <PageContainer>
      <div className="flex flex-wrap items-end justify-between gap-3.5">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[.1em] text-tx3">
            <span className="h-0.5 w-3.5 bg-ac" />
            Sales & Billing · Invoice editor
          </div>
          <h1 className="m-0 text-[24px] font-semibold tracking-[-.015em]">{id ? 'Edit draft invoice' : 'Create invoice'}</h1>
          <div className="text-[13px] text-tx2">
            {id ? 'Drafts can be edited freely. Issued invoices are locked and corrected with credit notes.' : 'Build the invoice on the left — the branded document updates live on the right.'}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={() => router.push(id ? `/sales/invoices/${id}` : '/sales/invoices')}>
            Cancel
          </Button>
          <Button icon="save" disabled={busy || !customerId} onClick={() => void save(false)}>
            Save draft
          </Button>
          {can('invoices.issue') && (
            <Button variant="primary" icon="send" disabled={busy || !customerId || !calc.result} onClick={() => void save(true)}>
              Save & issue
            </Button>
          )}
        </div>
      </div>
      {error && <Banner tone="err">{error}</Banner>}
      <div className="grid items-start gap-[18px]" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 520px), 1fr))' }}>
        <div className="flex min-w-0 flex-col gap-[18px]">
          <Section n="01" title="Customer & dates">
            <div className="grid grid-cols-6 gap-3.5 p-4 max-sm:grid-cols-1">
              <div className="col-span-4 max-sm:col-span-1">
                <Field label="Customer" htmlFor="ie-customer" required>
                  <Select id="ie-customer" aria-label="Customer" value={customerId} onChange={(e) => { change(setCustomerId)(e.target.value); const c = customers.data?.results.find((x) => String(x.id) === e.target.value); if (c && !id) setCurrency(c.currency); setProjectId(''); }}>
                    <option value="">Select customer</option>
                    {customers.data?.results.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} · {c.currency}
                      </option>
                    ))}
                  </Select>
                </Field>
                {can('sales.manage') && (
                  <button type="button" className="mt-1 bg-transparent p-0 text-[11.5px] font-medium text-lk" onClick={() => setNewCustomer(true)}>
                    + New customer
                  </button>
                )}
              </div>
              <div className="col-span-2 max-sm:col-span-1">
                <Field label="Currency" htmlFor="ie-currency">
                  <Select id="ie-currency" aria-label="Currency" value={currency} onChange={(e) => change(setCurrency)(e.target.value)}>
                    {(config.data?.enabled_currencies ?? []).map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              {customer && (
                <div className="col-span-6 flex gap-3 border border-bd bg-sf2 px-3 py-2.5 text-[12px] leading-[1.5] text-tx2 max-sm:col-span-1">
                  <Icon name="location_on" size={17} className="text-tx3" />
                  <span className="whitespace-pre-line">{[customer.name, customer.address, [customer.city, customer.country].filter(Boolean).join(', '), customer.tax_id].filter(Boolean).join('\n')}</span>
                </div>
              )}
              <div className="col-span-2 max-sm:col-span-1">
                <Field label="Invoice number" htmlFor="ie-number">
                  <Input id="ie-number" aria-label="Invoice number" disabled value="Assigned on issue" className="font-mono" />
                </Field>
              </div>
              <div className="col-span-2 max-sm:col-span-1">
                <Field label="Invoice date" htmlFor="ie-date" required>
                  <Input id="ie-date" type="date" aria-label="Invoice date" value={issueDate} onChange={(e) => change(setIssueDate)(e.target.value)} />
                </Field>
              </div>
              <div className="col-span-2 max-sm:col-span-1">
                <Field label="Due date" htmlFor="ie-due">
                  <Input id="ie-due" type="date" aria-label="Due date" value={dueDate} onChange={(e) => { setDueTouched(true); change(setDueDate)(e.target.value); }} />
                </Field>
              </div>
              <div className="col-span-3 max-sm:col-span-1">
                <Field label="Customer PO reference" htmlFor="ie-ref">
                  <Input id="ie-ref" aria-label="Customer PO reference" placeholder="Optional" value={reference} onChange={(e) => change(setReference)(e.target.value)} />
                </Field>
              </div>
              <div className="col-span-3 flex flex-col justify-end text-[11.5px] leading-[1.45] text-tx3 max-sm:col-span-1">
                {customer ? `Net ${customer.payment_terms_days} days from the customer profile` : 'Choose a customer to apply their payment terms.'}
              </div>
            </div>
          </Section>
          <Section n="02" title="Billing source & project">
            <div className="flex flex-col gap-3.5 p-4">
              <Segmented
                label="Billing source"
                value={source}
                onChange={(v) => change(setSource)(v)}
                options={[
                  { value: 'standard', label: 'Standard' },
                  { value: 'project', label: 'Project' },
                  { value: 'milestone', label: 'Milestone' },
                  { value: 'order', label: 'Sales order' },
                ]}
              />
              <div className="text-[12px] leading-[1.5] text-tx3">
                {source === 'standard' && 'Services from the billing items list or free-text lines.'}
                {source === 'project' && 'Bill project work against a project reference. Add any number of lines.'}
                {source === 'milestone' && "Select a milestone — its exact share of the contract becomes the line. A milestone can be invoiced only once."}
                {source === 'order' && 'Invoice the remaining quantities of a confirmed sales order. Ordered quantities can never be over-invoiced.'}
              </div>
              {(source === 'project' || source === 'milestone') && (
                <Field label="Project" htmlFor="ie-project">
                  <Select id="ie-project" aria-label="Project" value={projectId} onChange={(e) => change(setProjectId)(e.target.value)}>
                    <option value="">— No project —</option>
                    {projects.data?.results.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.reference} · {p.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {source === 'milestone' && project && (
                <div className="border border-bd">
                  <div className="flex items-center justify-between border-b border-bd bg-sf2 px-3 py-2 text-[10.5px] font-semibold uppercase tracking-[.08em] text-tx3">
                    Milestones · contract {money(project.contract_value, project.currency)}
                    <Link href={`/sales/projects/${project.id}`} className="text-[11.5px] font-medium normal-case tracking-normal">
                      Manage milestones
                    </Link>
                  </div>
                  {project.milestones.length ? (
                    project.milestones.map((m) => {
                      const taken = billedMilestones.get(m.id);
                      return (
                        <button
                          key={m.id}
                          type="button"
                          disabled={busy || Boolean(taken)}
                          onClick={() => void fromSource({ milestone_id: m.id })}
                          className="grid w-full grid-cols-[minmax(0,1fr)_70px_140px_150px] items-center gap-2.5 border-b border-bd bg-transparent px-3 py-[9px] text-left text-[12.5px] text-tx last:border-b-0 hover:bg-sfh disabled:opacity-50"
                        >
                          <span className="font-medium">{m.name}</span>
                          <span className="text-tx3">{trimDecimal(m.percent)}%</span>
                          <span className="text-right font-semibold tabular-nums">{money(m.amount, project.currency)}</span>
                          <span className={`text-right text-[11.5px] ${taken ? 'text-tx3' : 'text-lk'}`}>
                            {taken ? `Billed · ${taken.number ?? 'draft'}` : 'Create milestone draft →'}
                          </span>
                        </button>
                      );
                    })
                  ) : (
                    <div className="px-3 py-3 text-[12px] text-tx3">This project has no milestones yet.</div>
                  )}
                </div>
              )}
              {source === 'order' && (
                <div className="border border-bd">
                  {orders.data?.results.filter((o) => o.status === 'confirmed' || o.status === 'partially_invoiced').length ? (
                    orders.data.results
                      .filter((o) => o.status === 'confirmed' || o.status === 'partially_invoiced')
                      .map((o) => (
                        <button
                          key={o.id}
                          type="button"
                          disabled={busy}
                          onClick={() => void fromSource({ order_id: o.id })}
                          className="grid w-full grid-cols-[140px_minmax(0,1fr)_120px] items-center gap-2.5 border-b border-bd bg-transparent px-3 py-[9px] text-left text-[12.5px] text-tx last:border-b-0 hover:bg-sfh"
                        >
                          <span className="font-mono">{o.number}</span>
                          <span className="truncate">{o.title || formatDate(o.order_date)}</span>
                          <span className="text-right text-[11.5px] text-lk">Invoice remaining →</span>
                        </button>
                      ))
                  ) : (
                    <div className="px-3 py-3 text-[12px] text-tx3">{customerId ? 'No confirmed sales orders for this customer.' : 'Choose a customer first.'}</div>
                  )}
                </div>
              )}
            </div>
          </Section>
          <Section n="03" title="Line items" aside="Billing items or free-text lines — no catalog record required">
            <LinesEditor lines={lines} onChange={change(setLines)} currency={currency} calc={calc.result} accountKind="revenue" />
            <div className="flex flex-wrap items-start justify-between gap-4 border-t border-bd px-4 pt-3 pb-4">
              <div className="flex flex-col gap-3">
                <Button size="sm" icon="add" onClick={() => change(setLines)([...lines, blankLine(lines[lines.length - 1]?.tax_code_id ?? '')])}>
                  Add line
                </Button>
                <Checkbox checked={inclusive} onChange={change(setInclusive)} label="Prices include tax" hint="Tax is extracted from the line amounts instead of added on top." />
                <div className="flex items-end gap-2">
                  <Field label="Document discount" htmlFor="ie-discount">
                    <AmountInput id="ie-discount" aria-label="Document discount" controlSize="sm" value={discountValue} onChange={(e) => change(setDiscountValue)(e.target.value)} />
                  </Field>
                  <Segmented size="sm" label="Discount type" value={discountType} onChange={change(setDiscountType)} options={[{ value: 'percent', label: '%' }, { value: 'fixed', label: 'Amount' }]} />
                </div>
              </div>
              <Totals calc={calc.result} currency={currency} error={calc.error} />
            </div>
          </Section>
          <Section n="04" title="Notes">
            <div className="flex flex-col gap-3 p-4">
              <Field label="Notes on the invoice" htmlFor="ie-notes">
                <Textarea id="ie-notes" aria-label="Notes on the invoice" rows={3} value={notes} onChange={(e) => change(setNotes)(e.target.value)} />
              </Field>
              <p className="m-0 text-[11.5px] text-tx3">
                Terms, payment instructions, signature and footer come from the published branding version and are frozen on the invoice when it is issued.
              </p>
            </div>
          </Section>
        </div>
        <section className="sticky top-4 flex flex-col border border-bd bg-sf">
          <header className="flex items-center justify-between border-b border-bd px-4 py-3">
            <div>
              <div className="text-[13px] font-semibold">Live preview</div>
              <div className="text-[11.5px] text-tx3">
                {branding.data?.version ? `Template ${branding.data.config.invoice_template} · version ${branding.data.version} (current)` : 'No published branding'}
              </div>
            </div>
            {can('branding.manage') && (
              <Link href="/settings/branding" className="text-[12px] font-medium">
                Branding →
              </Link>
            )}
          </header>
          <div className="flex justify-center overflow-hidden bg-sf3 p-4">
            <InvoicePaper view={view} number="Assigned on issue" scale={0.6} watermark="DRAFT" />
          </div>
        </section>
      </div>
      {newCustomer && (
        <CustomerDrawer
          onClose={(created) => {
            setNewCustomer(false);
            if (created && typeof created === 'object' && 'id' in created) {
              setCustomerId(String((created as Customer).id));
              setCurrency((created as Customer).currency);
            }
          }}
        />
      )}
    </PageContainer>
  );
}
