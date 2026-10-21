'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Badge, type Tone } from '@/components/ui/Badge';
import { Banner } from '@/components/ui/Banner';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Choice';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field } from '@/components/ui/Field';
import { AmountInput, Input, Select, Textarea } from '@/components/ui/Input';
import { Cell, DialogActions, DialogFooter, Drawer, FormGrid } from '@/components/ui/Overlay';
import { PageContainer, PageHeader } from '@/components/ui/PageHeader';
import { Panel } from '@/components/ui/Panel';
import { FilterChips, Pager, TableState, TableToolbar } from '@/components/ui/TableKit';
import { TBody, TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { toast } from '@/components/ui/Toast';
import { api, errorMessage } from '@/lib/api/client';
import { APPROVAL_INBOX_KEY } from '@/lib/api/hooks';
import { invalidate, useQuery } from '@/lib/api/query';
import type { ApprovalPolicy, ApprovalRequest, Page, Role } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthProvider';
import { formatDateTime } from '@/lib/format';
import { useFormState } from '@/lib/forms';

const STATUS_TONE: Record<ApprovalRequest['status'], Tone> = { pending: 'warn', approved: 'ok', rejected: 'err', cancelled: 'neutral' };
type StatusFilter = 'pending' | 'approved' | 'rejected' | 'cancelled' | 'all';

export function ApprovalsPage() {
  const { can } = useAuth();
  return (
    <PageContainer>
      <PageHeader eyebrow="Settings" title="Approvals" description="Simple approval rules and the requests waiting for a decision. Decisions are recorded in the audit log." />
      <RequestsTable />
      {can('approvals.manage') && <RulesTable />}
    </PageContainer>
  );
}

function RequestsTable() {
  const { user } = useAuth();
  const [status, setStatus] = useState<StatusFilter>('pending');
  const [page, setPage] = useState(1);
  const params = { status: status === 'all' ? '' : status, page };
  const key = `/approvals/requests/?status=${params.status}&page=${page}`;
  const query = useQuery(key, () => api.get<Page<ApprovalRequest>>('/approvals/requests/', params));
  const [decision, setDecision] = useState<{ request: ApprovalRequest; approve: boolean } | null>(null);
  const [withdraw, setWithdraw] = useState<ApprovalRequest | null>(null);

  const after = (message: string) => {
    invalidate('/approvals/');
    invalidate(APPROVAL_INBOX_KEY);
    invalidate('/branding/');
    invalidate('/accounting/');
    invalidate('/banking/');
      for (const prefix of ['/sales/', '/billing/', '/purchasing/', '/documents/', '/founders/', '/ownership/']) invalidate(prefix);
    toast(message);
  };

  const data = query.data;
  return (
    <Panel>
      <TableToolbar title="Approval requests" subtitle="Requests you made, and requests you are allowed to decide.">
        <FilterChips label="Status" value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={[
          { value: 'pending', label: 'Pending' }, { value: 'approved', label: 'Approved' }, { value: 'rejected', label: 'Rejected' },
          { value: 'cancelled', label: 'Withdrawn' }, { value: 'all', label: 'All' },
        ]} />
      </TableToolbar>
      <Table>
        <THead>
          <TR>
            <TH>Request</TH>
            <TH>Requested by</TH>
            <TH>Status</TH>
            <TH>Decision</TH>
            <TH align="right"><span className="sr-only">Actions</span></TH>
          </TR>
        </THead>
        <TBody>
          <TableState colSpan={5} loading={query.loading && !data} error={query.error ? errorMessage(query.error) : null} empty={data?.count === 0 ? (status === 'pending' ? 'Nothing waiting for approval.' : 'No requests.') : null}>
            {data?.results.map((r) => (
              <TR key={r.id}>
                <TD>
                  <div className="font-medium">{r.title}</div>
                  {r.summary.journal_id && <Link href={`/banking/journals/${r.summary.journal_id}`} className="text-[12px]">Review journal lines →</Link>}
                    {r.summary.record_url && <Link href={r.summary.record_url} className="text-[12px]">Review financial record →</Link>}
                  {r.request_reason && <div className="text-[11.5px] text-tx3">“{r.request_reason}”</div>}
                </TD>
                <TD>
                  <div>{r.requested_by.display_name}</div>
                  <div className="text-[11.5px] text-tx3">{formatDateTime(r.requested_at)}</div>
                </TD>
                <TD><Badge tone={STATUS_TONE[r.status]}>{r.status === 'cancelled' ? 'Withdrawn' : r.status}</Badge>{r.category==='ownership_changes' && <div className="mt-1 text-[11px] text-tx3">{r.vote_count ?? 0}/{r.required_approvals ?? 1} independent approvals · separate shareholder consent required</div>}</TD>
                <TD className="text-tx2">
                  {r.reviewed_by ? (
                    <>
                      <div>{r.reviewed_by.display_name} · {formatDateTime(r.reviewed_at)}</div>
                      {r.decision_reason && <div className="text-[11.5px] text-tx3">“{r.decision_reason}”</div>}
                      {r.result_reference && <div className="font-mono text-[11px] text-tx3">{r.result_reference}</div>}
                    </>
                  ) : '—'}
                </TD>
                <TD align="right">
                  <span className="inline-flex gap-1">
                    {r.can_decide && (
                      <>
                        <Button size="xs" variant="danger" onClick={() => setDecision({ request: r, approve: false })}>Reject</Button>
                        <Button size="xs" variant="primary" onClick={() => setDecision({ request: r, approve: true })}>Approve</Button>
                      </>
                    )}
                    {r.status === 'pending' && r.requested_by.id === user.id && <Button size="xs" onClick={() => setWithdraw(r)}>Withdraw</Button>}
                  </span>
                </TD>
              </TR>
            ))}
          </TableState>
        </TBody>
      </Table>
      {data && <Pager page={data.page} totalPages={data.total_pages} count={data.count} pageSize={data.page_size} onPage={setPage} />}

      <ConfirmDialog
        open={decision !== null}
        title={decision?.approve ? `Approve “${decision.request.title}”?` : `Reject “${decision?.request.title}”?`}
        confirmLabel={decision?.approve ? 'Approve' : 'Reject'}
        danger={!decision?.approve}
        reason={decision?.approve ? 'optional' : 'required'}
        reasonLabel={decision?.approve ? 'Comment (optional)' : 'Reason for rejecting'}
        onCancel={() => setDecision(null)}
        onConfirm={async (reason) => {
          if (!decision) return;
          const result = await api.post<ApprovalRequest>(`/approvals/requests/${decision.request.id}/${decision.approve ? 'approve' : 'reject'}/`, { reason });
          after(decision.approve ? result.status==='pending' ? 'Vote recorded — further independent approvals required' : result.category==='ownership_changes' ? 'Proposal approved — documented register confirmation is still required' : 'Approved — the change has been applied' : 'Request rejected');
          setDecision(null);
        }}
      >
        {decision?.approve ? 'Approving applies exactly the change that was submitted.' : 'The requester sees your reason. Nothing is changed.'}
      </ConfirmDialog>
      <ConfirmDialog
        open={withdraw !== null}
        title="Withdraw this request?"
        confirmLabel="Withdraw"
        onCancel={() => setWithdraw(null)}
        onConfirm={async () => {
          if (!withdraw) return;
          await api.post(`/approvals/requests/${withdraw.id}/cancel/`);
          after('Request withdrawn');
          setWithdraw(null);
        }}
      >
        The request is closed without a decision. You can submit a new one later.
      </ConfirmDialog>
    </Panel>
  );
}

function RulesTable() {
  const policies = useQuery('/approvals/policies/', () => api.get<ApprovalPolicy[]>('/approvals/policies/'));
  const roles = useQuery('/roles/', () => api.get<Role[]>('/roles/'));
  const [editing, setEditing] = useState<ApprovalPolicy | null>(null);
  return (
    <Panel>
      <TableToolbar title="Rules" subtitle="One simple rule per category. Rules for modules that are not built yet are stored and applied when the module ships." />
      <Table>
        <THead>
          <TR>
            <TH>Rule</TH>
            <TH>Enforcement</TH>
            <TH>Approval</TH>
            <TH>Approver role</TH>
            <TH align="right">Threshold</TH>
            <TH>Self-approval</TH>
            <TH align="right"><span className="sr-only">Actions</span></TH>
          </TR>
        </THead>
        <TBody>
          <TableState colSpan={7} loading={policies.loading && !policies.data} error={policies.error ? errorMessage(policies.error) : null}>
            {policies.data?.map((p) => (
              <TR key={p.category}>
                <TD>
                  <div className="font-medium">{p.label}</div>
                  <div className="text-[11.5px] text-tx3">{p.description}</div>
                </TD>
                <TD>{p.enforced ? <Badge tone="ok">Enforced now</Badge> : <Badge tone="neutral">{`Stored · Phase ${p.phase}`}</Badge>}</TD>
                <TD>{p.is_required && p.is_active ? <Badge tone="warn">Required</Badge> : <span className="text-tx3">{p.is_required ? 'Rule inactive' : 'Not required'}</span>}</TD>
                <TD>{p.approver_role?.name ?? 'Administrators'}</TD>
                <TD align="right">{p.supports_threshold ? (p.amount_threshold ?? 'Any amount') : '—'}</TD>
                <TD>{p.allow_self_approval ? 'Allowed' : 'Not allowed'}</TD>
                <TD align="right"><Button size="xs" onClick={() => setEditing(p)}>Edit</Button></TD>
              </TR>
            ))}
          </TableState>
        </TBody>
      </Table>
      {editing && roles.data && (
        <PolicyDrawer
          policy={editing}
          roles={roles.data}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            invalidate('/approvals/');
            invalidate('/branding/');
            toast('Approval rule saved');
          }}
        />
      )}
    </Panel>
  );
}

interface PolicyForm extends Record<string, unknown> {
  required_approvals: string;
  is_required: boolean;
  is_active: boolean;
  approver_role: string;
  amount_threshold: string;
  allow_self_approval: boolean;
  notes: string;
}

function PolicyDrawer({ policy, roles, onClose, onSaved }: { policy: ApprovalPolicy; roles: Role[]; onClose: () => void; onSaved: () => void }) {
  const form = useFormState<PolicyForm>({
    required_approvals: String(policy.required_approvals ?? 1),
    is_required: policy.is_required,
    is_active: policy.is_active,
    approver_role: policy.approver_role ? String(policy.approver_role.id) : '',
    amount_threshold: policy.amount_threshold ?? '',
    allow_self_approval: policy.allow_self_approval,
    notes: policy.notes,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { values, set, errors } = form;

  const save = async () => {
    if (values.amount_threshold && !/^\d{1,16}(\.\d{1,2})?$/.test(values.amount_threshold)) {
      form.setErrors({ amount_threshold: 'Enter an amount such as 50000.00' });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/approvals/policies/${policy.category}/`, {
        ...(policy.category==='ownership_changes' ? {required_approvals:Number(values.required_approvals)} : {}),
        is_required: values.is_required,
        is_active: values.is_active,
        approver_role: values.approver_role ? Number(values.approver_role) : null,
        ...(policy.supports_threshold ? { amount_threshold: values.amount_threshold || null } : {}),
        allow_self_approval: values.allow_self_approval,
        notes: values.notes,
      });
      onSaved();
    } catch (err) {
      setError(form.applyError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer open onClose={onClose} width={520} eyebrow="Approval rule" title={policy.label} description={policy.description}
      footer={
        <DialogFooter>
          {!policy.enforced && <Banner tone="info" compact>{`Stored now and enforced when this module is delivered (Phase ${policy.phase}). Nothing is approved through this rule yet.`}</Banner>}
          {error && <Banner tone="err" compact>{error}</Banner>}
          <DialogActions>
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" onClick={() => void save()} disabled={busy || !form.dirty}>{busy ? 'Saving…' : 'Save rule'}</Button>
          </DialogActions>
        </DialogFooter>
      }>
      <FormGrid>
        {policy.category==='ownership_changes' && <Cell><Field htmlFor="ownership-quorum" label="Required distinct independent approvals" hint="Shareholder consent is separate. A later policy edit cannot reduce requirements on an existing proposal."><Input id="ownership-quorum" type="number" min="1" max="20" value={values.required_approvals} onChange={e=>set('required_approvals',e.target.value)}/></Field></Cell>}
        <Cell><Checkbox disabled={policy.category==='ownership_changes'} checked={values.is_required} onChange={(v) => set('is_required', v)} label="Approval required" hint={policy.category==='ownership_changes' ? 'Ownership always requires affected-party authorization and independent review.' : 'Actions in this category wait for an approver before taking effect.'} /></Cell>
        <Cell><Checkbox disabled={policy.category==='ownership_changes'} checked={values.is_active} onChange={(v) => set('is_active', v)} label="Rule active" /></Cell>
        <Cell>
          <Field label="Designated approver role" htmlFor="p-role" error={errors.approver_role} hint="Members of this role (and Administrators) can decide requests.">
            <Select id="p-role" value={values.approver_role} onChange={(e) => set('approver_role', e.target.value)}>
              <option value="">Administrators only</option>
              {roles.filter((r) => r.is_active && !r.is_admin).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </Select>
          </Field>
        </Cell>
        {policy.supports_threshold && (
          <Cell>
            <Field label="Amount threshold (optional)" htmlFor="p-threshold" error={errors.amount_threshold} hint="Only amounts at or above this need approval. Leave empty for all amounts.">
              <AmountInput id="p-threshold" placeholder="0.00" value={values.amount_threshold} invalid={Boolean(errors.amount_threshold)} onChange={(e) => set('amount_threshold', e.target.value.trim())} />
            </Field>
          </Cell>
        )}
        <Cell><Checkbox disabled={policy.category==='ownership_changes'} checked={values.allow_self_approval} onChange={(v) => set('allow_self_approval', v)} label="Allow requesters to approve their own requests" hint="Off by default — a second person should review." /></Cell>
        <Cell>
          <Field label="Notes" htmlFor="p-notes" error={errors.notes}>
            <Textarea id="p-notes" rows={3} maxLength={500} value={values.notes} onChange={(e) => set('notes', e.target.value)} />
          </Field>
        </Cell>
      </FormGrid>
    </Drawer>
  );
}
