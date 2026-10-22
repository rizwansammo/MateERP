'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { InfoPanel, InfoPanels } from '@/components/ui/InfoPanel';
import { StatGrid } from '@/components/ui/StatGrid';
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { TableToolbar } from '@/components/ui/TableKit';
import { Panel } from '@/components/ui/Panel';
import { api } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDate } from '@/lib/format';

import { useConfig } from '@/features/accounting/shared';
import { FormDrawer, type FormValues, Screen, body } from '@/features/commerce/forms';
import { ListPanel, Primary, positive, sumDecimals, useApi, useMoney } from '@/features/commerce/shared';
import type { Contact, Customer, Project } from '@/features/commerce/types';

import { InvoiceTable, PaymentTable } from './tables';

const EYEBROW = 'Sales & Billing';

export function CustomersPage() {
  const { can } = useAuth();
  const money = useMoney();
  const router = useRouter();
  const [edit, setEdit] = useState(false);
  useEffect(() => { const timer = window.setTimeout(() => { if (new URLSearchParams(window.location.search).get('new') === '1' && can('sales.manage')) setEdit(true); }, 0); return () => window.clearTimeout(timer); }, [can]);
  return (
    <Screen
      eyebrow={EYEBROW}
      title="Customers"
      description="Financial customer records — billing identity, terms, balances and history."
      actions={
        can('sales.manage') && (
          <Button variant="primary" icon="person_add" onClick={() => setEdit(true)}>
            New customer
          </Button>
        )
      }
    >
      <ListPanel<Customer>
        path="/sales/customers/"
        search="Search customers…"
        filters={[
          { value: 'all', label: 'All' },
          { value: 'active', label: 'Active', query: 'status=active' },
          { value: 'inactive', label: 'Inactive', query: 'status=inactive' },
        ]}
        empty="No customers yet. Create your first customer to start invoicing."
        columns={[
          {
            key: 'name',
            label: 'Customer',
            render: (c) => (
              <Primary href={`/sales/customers/${c.id}`} title={c.name} sub={[c.code, c.contact_name, c.email].filter(Boolean).join(' · ')} />
            ),
          },
          { key: 'loc', label: 'Location', render: (c) => [c.city, c.country].filter(Boolean).join(', ') || '—' },
          { key: 'ccy', label: 'Currency', className: 'font-mono', render: (c) => c.currency },
          { key: 'terms', label: 'Terms', render: (c) => `Net ${c.payment_terms_days}` },
          {
            key: 'out',
            label: 'Outstanding',
            align: 'right',
            render: (c) => {
              const rows = Object.entries(c.balances ?? {});
              return rows.length ? (
                <div className="flex flex-col items-end">
                  {rows.map(([cur, b]) => (
                    <span key={cur} className={positive(b.overdue) ? 'font-semibold text-err' : 'font-semibold'}>
                      {money(b.outstanding, cur)}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="text-tx3">—</span>
              );
            },
          },
          { key: 'status', label: 'Status', render: (c) => (c.is_active ? <Badge tone="ok">Active</Badge> : <Badge>Inactive</Badge>) },
        ]}
      />
      {edit && (
        <CustomerDrawer
          onClose={(created) => {
            setEdit(false);
            if (created && typeof created === 'object' && 'id' in created) router.push(`/sales/customers/${(created as Customer).id}`);
          }}
        />
      )}
    </Screen>
  );
}

export function CustomerDrawer({ customer, onClose }: { customer?: Customer; onClose: (result?: unknown) => void }) {
  const config = useConfig();
  const currencies = config.data?.enabled_currencies ?? [];
  const initial: FormValues = {
    name: customer?.name ?? '',
    contact_name: customer?.contact_name ?? '',
    email: customer?.email ?? '',
    phone: customer?.phone ?? '',
    tax_id: customer?.tax_id ?? '',
    address: customer?.address ?? '',
    city: customer?.city ?? '',
    country: customer?.country ?? '',
    currency: customer?.currency ?? config.data?.base_currency ?? '',
    payment_terms_days: String(customer?.payment_terms_days ?? 30),
    notes: customer?.notes ?? '',
    is_active: customer?.is_active ?? true,
  };
  return (
    <FormDrawer
      title={customer ? `Edit ${customer.name}` : 'New customer'}
      eyebrow={EYEBROW}
      initial={initial}
      success={customer ? 'Customer updated' : 'Customer created'}
      fields={[
        { key: 'name', label: 'Customer / legal name', required: true, w: 'full' },
        { key: 'contact_name', label: 'Billing contact' },
        { key: 'email', label: 'Email', type: 'email' },
        { key: 'phone', label: 'Phone' },
        { key: 'tax_id', label: 'Tax registration (BIN / VAT / UEN)' },
        { key: 'address', label: 'Billing address', type: 'textarea' },
        { key: 'city', label: 'City', w: 'third' },
        { key: 'country', label: 'Country', w: 'third' },
        { key: 'currency', label: 'Default currency', type: 'select', w: 'third', options: currencies.map((c) => ({ value: c, label: c })) },
        { key: 'payment_terms_days', label: 'Payment terms (days)', type: 'number' },
        { key: 'notes', label: 'Notes', type: 'textarea' },
        ...(customer ? [{ key: 'is_active', label: 'Active — available on new documents', type: 'checkbox' as const, w: 'full' as const }] : []),
      ]}
      onSave={(v) => {
        const data = body(v, ['payment_terms_days']);
        return customer ? api.patch(`/sales/customers/${customer.id}/`, data) : api.post('/sales/customers/', data);
      }}
      onClose={onClose}
    />
  );
}

function ContactDrawer({ customerId, contact, onClose }: { customerId: number; contact?: Contact; onClose: () => void }) {
  return (
    <FormDrawer
      title={contact ? `Edit ${contact.name}` : 'New contact'}
      eyebrow="Customer contact"
      width={520}
      initial={{
        name: contact?.name ?? '',
        role: contact?.role ?? '',
        email: contact?.email ?? '',
        phone: contact?.phone ?? '',
        is_primary: contact?.is_primary ?? false,
        is_active: contact?.is_active ?? true,
      }}
      success="Contact saved"
      fields={[
        { key: 'name', label: 'Name', required: true, w: 'full' },
        { key: 'role', label: 'Role' },
        { key: 'email', label: 'Email', type: 'email' },
        { key: 'phone', label: 'Phone' },
        { key: 'is_primary', label: 'Primary billing contact', type: 'checkbox', w: 'full' },
        { key: 'is_active', label: 'Active', type: 'checkbox', w: 'full' },
      ]}
      onSave={(v) =>
        contact
          ? api.patch(`/sales/customers/${customerId}/contacts/${contact.id}/`, v)
          : api.post(`/sales/customers/${customerId}/contacts/`, v)
      }
      onClose={onClose}
    />
  );
}

interface Account {
  balances: { currency: string; outstanding: string; overdue: string; credit?: string }[];
  credit: { currency: string; amount: string }[];
  statement: { date: string; currency: string; kind: string; number: string; debit: string; credit: string; balance: string; ref: string }[];
}

export function CustomerDetail({ id }: { id: string }) {
  const { can } = useAuth();
  const money = useMoney();
  const customer = useApi<Customer>(`/sales/customers/${id}/`);
  const account = useApi<Account>(`/billing/customers/${id}/account/`);
  const projects = useApi<{ results: Project[] }>(`/sales/projects/?customer=${id}&page_size=50`);
  const [edit, setEdit] = useState(false);
  const [contact, setContact] = useState<Contact | 'new' | null>(null);
  const c = customer.data;
  if (!c) return <Screen eyebrow="Customer" title={customer.error ? 'Customer not found' : 'Loading…'} />;
  const cur = c.currency;
  const balance = account.data?.balances.find((b) => b.currency === cur);
  const billed = account.data?.statement.filter((r) => r.kind === 'Invoice' && r.currency === cur);
  const sum = (rows: { debit: string; credit: string }[] | undefined, key: 'debit' | 'credit') =>
    sumDecimals((rows ?? []).map((r) => r[key]));
  const statementCur = account.data?.statement.filter((r) => r.currency === cur) ?? [];
  return (
    <Screen
      eyebrow="Customer"
      title={c.name}
      description={[c.contact_name, c.email, [c.city, c.country].filter(Boolean).join(', ')].filter(Boolean).join(' · ')}
      meta={[
        { label: 'Code', value: c.code },
        { label: 'Currency', value: cur },
        { label: 'Terms', value: `Net ${c.payment_terms_days}` },
        { label: 'Customer since', value: formatDate(c.created_at) },
      ]}
      actions={
        <>
          {can('sales.manage') && (
            <Button icon="edit" onClick={() => setEdit(true)}>
              Edit
            </Button>
          )}
          {can('invoices.create') && (
            <Link href={`/sales/invoices/new?customer=${c.id}`} className="inline-flex h-[34px] items-center gap-1.5 border border-pr bg-pr px-[14px] text-[12.5px] font-semibold text-prt hover:no-underline">
              New invoice
            </Link>
          )}
        </>
      }
    >
      <StatGrid
        minWidth={180}
        stats={[
          { label: 'Total billed', value: money(sum(billed, 'debit'), cur), sub: `${billed?.length ?? 0} issued invoices`, accentBar: true },
          {
            label: 'Received',
            value: money(sum(statementCur.filter((r) => r.kind === 'Payment'), 'credit'), cur),
            sub: 'Verified payments',
            accentBar: true,
          },
          {
            label: 'Credits',
            value: money(sum(statementCur.filter((r) => r.kind === 'Credit note'), 'credit'), cur),
            sub: account.data?.credit.length ? `Customer credit ${account.data.credit.map((x) => money(x.amount, x.currency)).join(', ')}` : 'Credit notes',
            accentBar: true,
          },
          {
            label: 'Outstanding',
            value: money(balance?.outstanding ?? '0', cur),
            tone: positive(balance?.overdue) ? 'err' : 'default',
            sub: positive(balance?.overdue) ? `${money(balance!.overdue, cur)} overdue` : 'Nothing overdue',
            accentBar: true,
          },
        ]}
      />
      <InfoPanels>
        <InfoPanel
          title="Billing profile"
          rows={[
            { label: 'Legal name', value: c.name },
            { label: 'Billing address', value: c.address },
            { label: 'Country', value: c.country },
            { label: 'Tax registration', value: c.tax_id },
          ]}
        />
        <InfoPanel
          title="Contact & terms"
          rows={[
            { label: 'Contact', value: c.contact_name },
            { label: 'Email', value: c.email },
            { label: 'Phone', value: c.phone },
            { label: 'Default currency', value: cur },
            { label: 'Payment terms', value: `${c.payment_terms_days} days` },
            { label: 'Notes', value: c.notes },
          ]}
        />
        <InfoPanel
          title="Projects"
          rows={
            projects.data?.results.length
              ? projects.data.results.map((p) => ({ label: p.reference, value: `${p.name}\n${money(p.contract_value, p.currency)}` }))
              : [{ label: 'None', value: '' }]
          }
        />
      </InfoPanels>
      <Panel>
        <TableToolbar title="Contacts" subtitle="People at this customer who receive invoices and statements">
          {can('sales.manage') && (
            <Button size="sm" icon="add" onClick={() => setContact('new')}>
              Add contact
            </Button>
          )}
        </TableToolbar>
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Role</TH>
              <TH>Email</TH>
              <TH>Phone</TH>
              <TH>Status</TH>
              <TH> </TH>
            </TR>
          </THead>
          <TBody>
            {c.contacts?.length ? (
              c.contacts.map((ct) => (
                <TR key={ct.id}>
                  <TD className="font-medium">
                    {ct.name} {ct.is_primary && <Badge tone="info">Primary</Badge>}
                  </TD>
                  <TD>{ct.role || '—'}</TD>
                  <TD>{ct.email || '—'}</TD>
                  <TD>{ct.phone || '—'}</TD>
                  <TD>{ct.is_active ? <Badge tone="ok">Active</Badge> : <Badge>Inactive</Badge>}</TD>
                  <TD align="right">
                    {can('sales.manage') && (
                      <Button size="xs" onClick={() => setContact(ct)}>
                        Edit
                      </Button>
                    )}
                  </TD>
                </TR>
              ))
            ) : (
              <TR>
                <TD colSpan={6} className="py-6 text-center text-tx3">
                  No contacts recorded.
                </TD>
              </TR>
            )}
          </TBody>
        </Table>
      </Panel>
      <InvoiceTable title="Invoices" customerId={c.id} hideCustomer />
      <PaymentTable title="Payments" customerId={c.id} hideCustomer />
      <Panel>
        <TableToolbar title="Customer statement" subtitle={`Running balance in ${cur} — invoices, payments, credits and refunds`} />
        <Table>
          <THead>
            <TR>
              <TH>Date</TH>
              <TH>Document</TH>
              <TH>Description</TH>
              <TH align="right">Debit</TH>
              <TH align="right">Credit</TH>
              <TH align="right">Balance</TH>
            </TR>
          </THead>
          <TBody>
            {statementCur.length ? (
              statementCur.map((r, i) => (
                <TR key={`${r.ref}-${i}`}>
                  <TD>{formatDate(r.date)}</TD>
                  <TD className="font-mono text-[12.5px]">{r.number}</TD>
                  <TD>{r.kind}</TD>
                  <TD align="right">{positive(r.debit) ? money(r.debit, cur) : ''}</TD>
                  <TD align="right">{positive(r.credit) ? money(r.credit, cur) : ''}</TD>
                  <TD align="right" className="font-semibold">
                    {money(r.balance, cur)}
                  </TD>
                </TR>
              ))
            ) : (
              <TR>
                <TD colSpan={6} className="py-6 text-center text-tx3">
                  No issued documents yet.
                </TD>
              </TR>
            )}
          </TBody>
        </Table>
      </Panel>
      {edit && <CustomerDrawer customer={c} onClose={() => setEdit(false)} />}
      {contact && <ContactDrawer customerId={c.id} contact={contact === 'new' ? undefined : contact} onClose={() => setContact(null)} />}
    </Screen>
  );
}
