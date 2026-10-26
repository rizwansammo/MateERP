'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Banner } from '@/components/ui/Banner';
import { Input, Select, AmountInput } from '@/components/ui/Input';
import { StatGrid } from '@/components/ui/StatGrid';
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table';
import { FormDrawer, Screen, body, type FormValues } from '@/features/commerce/forms';
import { act, Card, ListPanel, Primary, StatusBadge, useActionKey, useApi, useMoney, today } from '@/features/commerce/shared';
import { useConfig } from '@/features/accounting/shared';
import { FileViewer, type PrivateDocumentView } from '@/features/commerce/FileViewer';
import { EvidenceDrawer, EvidenceList, partyOptions, useParties, WeightEditor } from '@/features/founders/shared';
import { api, errorMessage } from '@/lib/api/client';
import { useAuth } from '@/lib/auth/AuthProvider';
import type { Page } from '@/lib/api/types';
import type { Capital, Holding, OwnershipSnapshot, Proposal, Register, ShareClass } from './types';

const percent = (value: string) => `${value.split('.')[0]}${value.includes('.') ? `.${value.split('.')[1]!.slice(0, 4)}` : ''}%`;

function CapTable({ holding, title }: { holding: Holding; title: string }) {
  const parties = useParties();
  return <Card title={title}><Table><THead><TR><TH>Holder</TH><TH align="right">Share units</TH><TH>Ownership</TH></TR></THead><TBody>
    {Object.entries(holding.units).map(([id, units]) => <TR key={id}>
      <TD>{parties.data?.results.find(p => p.id === Number(id))?.name ?? `Participant #${id}`}</TD><TD align="right">{String(units)}</TD>
      <TD><div className="mb-1">{percent(holding.percentages[id] ?? '0')}</div><div className="h-1 bg-sf3"><div className="h-1 bg-brand" style={{ width: `${Number(BigInt(units) * 10000n / BigInt(holding.total)) / 100}%` }} /></div></TD>
    </TR>)}
  </TBody></Table></Card>;
}

function SnapshotView({ snapshot }: { snapshot: OwnershipSnapshot }) {
  const parties = useParties();
  if ('weights' in snapshot.after) {
    return <Card title="Provisional agreement after amendment"><div className="divide-y divide-bd px-4">
      {Object.entries(snapshot.after.weights).map(([id, value]) => <div className="flex justify-between py-2" key={id}><span>{parties.data?.results.find(p => p.id === Number(id))?.name ?? id}</span><strong>{value}%</strong></div>)}
    </div></Card>;
  }
  return <>{Object.entries(snapshot.after).map(([id, holding]) => <CapTable key={id} holding={holding} title={`Preview after event · class #${id}`} />)}</>;
}

interface ProposalLine { transferor_id: string; recipient_id: string; units: string; percentage_points: string; price: string }
const emptyLine = (): ProposalLine => ({ transferor_id: '', recipient_id: '', units: '', percentage_points: '', price: '0' });

function ProposalDrawer({ kind, onClose }: { kind: string; onClose: () => void }) {
  const parties = useParties(); const classes = useApi<Page<ShareClass>>('/ownership/classes/?page_size=100'); const key = useActionKey();
  const [weights, setWeights] = useState<Record<string, string>>({}); const [lines, setLines] = useState<ProposalLine[]>([emptyLine()]);
  const [snapshot, setSnapshot] = useState<OwnershipSnapshot | null>(null); const [error, setError] = useState<string | null>(null); const [previewing, setPreviewing] = useState(false);
  const payload = (v: FormValues): Record<string, unknown> => {
    const data: Record<string, unknown> = { ...body(v), kind, client_key: key.key };
    if (kind === 'provisional') { delete data.share_class_id; data.weights = weights; }
    else data.lines = lines.map(line => ({ recipient_id: Number(line.recipient_id), ...(kind === 'transfer' ? { transferor_id: Number(line.transferor_id) } : {}), ...(line.percentage_points ? { percentage_points: line.percentage_points } : { units: line.units }), price: line.price }));
    return data;
  };
  const change = (index: number, field: keyof ProposalLine, value: string) => { setLines(lines.map((line, i) => i === index ? { ...line, [field]: value } : line)); setSnapshot(null); };
  const title = kind === 'provisional' ? 'Provisional ownership agreement / amendment' : kind === 'transfer' ? 'Propose atomic share transfer group' : kind === 'opening' ? 'Document existing formal register' : 'Propose share issuance';
  return <FormDrawer title={title} eyebrow="Ownership & Capital" width={1000} onClose={onClose} extraDirty={Object.keys(weights).length > 0 || lines.some(line => Boolean(line.units || line.recipient_id))}
    initial={{ title: '', effective_date: today(), share_class_id: '', rationale: '', legal_reference: '' }} fields={[
      { key: 'title', label: 'Proposal title', required: true }, { key: 'effective_date', label: 'Proposed effective date', type: 'date', required: true },
      ...(kind !== 'provisional' ? [{ key: 'share_class_id', label: 'Share class', type: 'select' as const, options: [{ value: '', label: 'Select configured class…' }, ...(classes.data?.results ?? []).map(c => ({ value: String(c.id), label: `${c.name} · ${c.currency}` }))] }] : []),
      { key: 'legal_reference', label: kind === 'provisional' ? 'Agreement reference' : 'Legal / register reference', required: true }, { key: 'rationale', label: 'Reason / supporting explanation', type: 'textarea', required: true },
    ]} onValues={() => setSnapshot(null)} onSave={v => api.post('/ownership/proposals/', payload(v))} success="Draft retained — attach evidence and collect participant authorization before review">
    {v => <div className="mt-4 space-y-4">
      {kind === 'provisional' ? <WeightEditor parties={parties.data?.results.filter(p => p.is_active) ?? []} values={weights} onChange={next => { setWeights(next); setSnapshot(null); }} /> : <div className="overflow-x-auto">
        <Table><THead><TR>{kind === 'transfer' && <TH>Authorizing transferor</TH>}<TH>Recipient</TH><TH>Whole units</TH>{kind === 'transfer' && <TH>OR company percentage points</TH>}<TH>Price per unit</TH><TH /></TR></THead><TBody>
          {lines.map((line, index) => <TR key={index}>
            {kind === 'transfer' && <TD><Select aria-label={`Transferor ${index + 1}`} value={line.transferor_id} onChange={e => change(index, 'transferor_id', e.target.value)}>{partyOptions(parties.data?.results).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></TD>}
            <TD><Select aria-label={`Recipient ${index + 1}`} value={line.recipient_id} onChange={e => change(index, 'recipient_id', e.target.value)}>{partyOptions(parties.data?.results).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></TD>
            <TD><Input aria-label={`Share units ${index + 1}`} inputMode="numeric" value={line.units} onChange={e => change(index, 'units', e.target.value)} /></TD>
            {kind === 'transfer' && <TD><AmountInput aria-label={`Company percentage points ${index + 1}`} value={line.percentage_points} onChange={e => change(index, 'percentage_points', e.target.value)} /></TD>}
            <TD><AmountInput aria-label={`Price per share ${index + 1}`} value={line.price} onChange={e => change(index, 'price', e.target.value)} /></TD>
            <TD><Button size="xs" disabled={lines.length === 1} onClick={() => { setLines(lines.filter((_, i) => i !== index)); setSnapshot(null); }}>Remove</Button></TD>
          </TR>)}
        </TBody></Table><Button className="mt-3" size="sm" onClick={() => { setLines([...lines, emptyLine()]); setSnapshot(null); }}>Add coordinated event line</Button>
      </div>}
      <Button disabled={previewing} onClick={async () => { setPreviewing(true); setError(null); try { setSnapshot(await api.post<OwnershipSnapshot>('/ownership/proposals/preview/', payload(v))); } catch (e) { setError(errorMessage(e)); } finally { setPreviewing(false); } }}>Preview exact ownership result</Button>
      {error && <Banner tone="err">{error}</Banner>}{snapshot && <SnapshotView snapshot={snapshot} />}
    </div>}
  </FormDrawer>;
}

export function OwnershipPage({ section }: { section: string }) {
  const [asOf,setAsOf]=useState(today());
  const { can } = useAuth(); const config = useConfig(); const money = useMoney(); const parties = useParties();
  const register = useApi<Register>(`/ownership/register/?date=${asOf}`); const capital = useApi<Capital>(section === 'capital' || section === 'overview' ? `/ownership/capital/?date=${asOf}` : null);
  const [kind, setKind] = useState<string | null>(null); const [newClass, setNewClass] = useState(false);
  const title = section === 'overview' ? 'Ownership overview' : section === 'capital' ? 'Capital records' : section === 'transfers' ? 'Share transfers' : section === 'issuance' ? 'Share issuance' : 'Ownership history';
  return <Screen eyebrow="Ownership & Capital" title={title} description="Ownership agreements, share capital, and history." actions={can('ownership.manage') && <div className="flex flex-wrap gap-2">
    <Button onClick={() => setKind('provisional')}>Amend provisional agreement</Button><Button onClick={() => setNewClass(true)}>Configure share class</Button><Button onClick={() => setKind('opening')}>Document existing register</Button>
    {['transfers', 'issuance', 'overview'].includes(section) && <Button variant="primary" onClick={() => setKind(section === 'transfers' ? 'transfer' : 'issuance')}>{section === 'transfers' ? 'Propose transfer group' : 'Propose issuance'}</Button>}
  </div>}>
    {Boolean(register.error || capital.error) && <Banner tone="err">{errorMessage(register.error || capital.error)}</Banner>}
    <div className="flex flex-wrap items-center gap-3"><label htmlFor="ownership-as-of" className="text-tx3">Ownership and capital as of</label><Input id="ownership-as-of" type="date" value={asOf} onChange={e=>setAsOf(e.target.value || today())}/></div>
    {['overview', 'history'].includes(section) && <Card title="Current provisional ownership agreement" subtitle={register.data?.provisional.effective_date ? `Effective ${register.data.provisional.effective_date} · agreement #${register.data.provisional.proposal_id}` : 'No confirmed provisional agreement'}>
      <div className="divide-y divide-bd px-4">{Object.entries(register.data?.provisional.weights ?? {}).map(([id, value]) => <div className="flex justify-between py-3" key={id}><span>{parties.data?.results.find(p => p.id === Number(id))?.name ?? id}</span><strong>{value}%</strong></div>)}
        {register.data && !register.data.provisional.proposal_id && <p className="py-4 text-tx3">No ownership agreement recorded.</p>}
      </div>
    </Card>}
    {['overview', 'capital'].includes(section) && capital.data?.classes.map(c => <div key={c.id} className="flex flex-col gap-[18px]">
      <StatGrid stats={[{ label: `${c.name} issued units`, value: String(c.register.total), accentBar: true }, { label: 'Recorded paid-in funding', value: money(c.paid_in, c.currency), accentBar: true }, { label: 'Unpaid subscription commitments', value: money(c.unpaid_commitments, c.currency), sub: 'No automatic company cash', accentBar: true }]} />
      <CapTable holding={c.register} title={`${c.name} · confirmed formal register`} /><p className="text-[12px] text-tx3">{c.rights ? `${c.rights} · ` : ''}Nominal capital: {c.nominal === null ? 'Not configured' : money(c.nominal, c.currency)}</p>
    </div>)}
    <ListPanel<Proposal> path={`/ownership/proposals/${section === 'transfers' ? '?kind=transfer' : section === 'issuance' ? '?kind=issuance' : ''}`} title="Proposals, agreements and historical events" columns={[
      { key: 'date', label: 'Effective date', render: p => p.effective_date }, { key: 'title', label: 'Proposal / agreement', render: p => <Primary href={`/ownership/history/${p.id}`} title={p.title} sub={p.kind === 'provisional' ? 'Provisional agreement amendment' : p.kind} /> },
      { key: 'ref', label: 'Evidence', render: p => `${p.legal_reference} · ${p.evidence.length} document(s)` }, { key: 'consent', label: 'Participant authorization', render: p => `${p.consents.length}/${p.snapshot.required_parties.length}` }, { key: 'status', label: 'Status', render: p => <StatusBadge status={p.status} /> },
    ]} />
    {kind && <ProposalDrawer kind={kind} onClose={() => setKind(null)} />}
    {newClass && <FormDrawer title="Configure formal share class" eyebrow="Documented legal structure" initial={{ name: '', currency: config.data?.base_currency ?? '', par_value: '', rights: '', is_active: true }} fields={[
      { key: 'name', label: 'Class name', required: true }, { key: 'currency', label: 'Subscription currency', type: 'select', options: (config.data?.enabled_currencies ?? []).map(value => ({ value, label: value })) },
      { key: 'par_value', label: 'Par value per share (optional)', type: 'amount' }, { key: 'rights', label: 'Economic / voting rights description', type: 'textarea' }, { key: 'is_active', label: 'Active', type: 'checkbox' },
    ]} onClose={() => setNewClass(false)} onSave={v => api.post('/ownership/classes/', { ...v, par_value: v.par_value || null })} />}
  </Screen>;
}

export function OwnershipDetail({ id }: { id: string }) {
  const [cancel,setCancel]=useState(false);
  const { can, user } = useAuth(); const query = useApi<Proposal>(`/ownership/proposals/${id}/`); const parties = useParties(); const p = query.data;
  const [upload, setUpload] = useState(false); const [consent, setConsent] = useState(false); const [file, setFile] = useState<PrivateDocumentView | null>(null);
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const run = async (action: string) => { if (busy) return; setBusy(true); setError(null); try { await act(() => api.post(`/ownership/proposals/${id}/${action}/`, {}), action === 'submit' ? 'Submitted for independent review' : 'Documented ownership event confirmed'); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } };
  const eligible = (parties.data?.results ?? []).filter(participant => p?.snapshot.required_parties.includes(participant.id) && !p.consents.some(c => c.party_id === participant.id) && (participant.user === user.id || !participant.user && can('ownership.attest')));
  return <Screen eyebrow="Ownership proposal / agreement" title={p?.title ?? 'Loading ownership record…'} description={p ? `${p.kind === 'provisional' ? 'Provisional agreement' : p.kind} · effective ${p.effective_date}` : ''} actions={p && <div className="flex flex-wrap gap-2">
    {p.status === 'draft' && <>{can('ownership.manage') && !p.consents.length && <Button onClick={() => setUpload(true)}>Attach authorization evidence</Button>}{eligible.length > 0 && <Button onClick={() => setConsent(true)}>Record participant authorization</Button>}{can('ownership.manage') && <Button variant="primary" disabled={busy} onClick={() => void run('submit')}>Submit for independent review</Button>}</>}
    {p.status === 'approved' && can('ownership.manage') && <Button variant="primary" disabled={busy} onClick={() => void run('confirm')}>Confirm documented effect</Button>}
    {['draft','approved'].includes(p.status) && can('ownership.manage') && <Button onClick={()=>setCancel(true)}>Cancel proposal</Button>}
  </div>}>
    {Boolean(error || query.error) && <Banner tone="err">{error ?? errorMessage(query.error)}</Banner>}
    {p && <><Card title="Workflow and evidence"><div className="grid gap-3 p-4 sm:grid-cols-3"><div><StatusBadge status={p.status} /></div><div>{p.consents.length}/{p.snapshot.required_parties.length} affected participants authorized</div><div>{p.approval ? <Link href="/settings/approvals">Review independent approvals #{p.approval}</Link> : 'Not submitted for independent review'}</div><div className="sm:col-span-3">{p.rationale}<div className="mt-2 text-tx3">Reference: {p.legal_reference}</div></div></div>
      <div className="divide-y divide-bd">{p.consents.map(c => <p key={c.party_id} className="px-4 py-2 text-[12px]">{parties.data?.results.find(participant => participant.id === c.party_id)?.name ?? c.party_id} · {c.mode === 'attestation' ? `External authorization recorded by user #${c.actor_id}` : `Authenticated shareholder user #${c.actor_id}`} · {c.reference}</p>)}</div>
    </Card><SnapshotView snapshot={p.snapshot} /><EvidenceList items={p.evidence} onView={f => setFile({ ...f, title: f.original_name, download_url: `${f.url}?download=1`, document_date: p.effective_date, label: 'Private ownership authorization evidence' })} /></>}
    {upload && <EvidenceDrawer target={{ proposal_id: Number(id) }} parties={parties.data?.results} onClose={() => setUpload(false)} />}{file && <FileViewer doc={file} onClose={() => setFile(null)} />}
    {consent && <FormDrawer title="Authorize ownership proposal" eyebrow="Shareholder / agreement participant consent" onClose={() => setConsent(false)} initial={{ party_id: String(eligible[0]?.id ?? ''), mode: 'authenticated', reference: '' }} fields={[
      { key: 'party_id', label: 'Affected participant', type: 'select', options: partyOptions(eligible) }, { key: 'mode', label: 'Authorization method', type: 'select', options: [{ value: 'authenticated', label: 'My linked shareholder account' }, { value: 'attestation', label: 'Authorized external attestation' }] }, { key: 'reference', label: 'Authorization and authority reference', type: 'textarea', required: true },
    ]} onSave={v => api.post(`/ownership/proposals/${id}/consent/`, body(v))} /> }
    {cancel && <FormDrawer title="Cancel ownership proposal" eyebrow="Retained proposal history" onClose={()=>setCancel(false)} initial={{reason:''}} fields={[{key:'reason',label:'Reason',type:'textarea',required:true}]} onSave={v=>api.post(`/ownership/proposals/${id}/cancel/`,v)}/>}
  </Screen>;
}
