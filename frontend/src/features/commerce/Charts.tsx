'use client';
import { minor } from '@/features/accounting/money';
import { Card, useMoney } from './shared';

export interface MonthlyPoint { month: string; [series: string]: string }
export interface Breakdown { label: string; amount: string; count?: number }
const COLORS = ['var(--c2)', 'var(--c1)', 'var(--c3)', 'var(--c4)', 'var(--c5)', 'var(--c6)'];
const abs = (n: bigint) => n < 0n ? -n : n;
/** Only a bounded display ratio becomes Number; all amounts remain integer/decimal strings. */
const ratio = (n: bigint, total: bigint) => total ? Number(n * 10000n / total) / 10000 : 0;
function axis(n: bigint) {
  const v = abs(n); const [scale, suffix] = v >= 100000000000n ? [100000000000n, 'L'] : v >= 1000000000n ? [1000000000n, 'K'] : [1000000n, ''];
  return `${n < 0 ? '−' : ''}${v / scale}${suffix && v % scale ? `.${v * 10n / scale % 10n}` : ''}${suffix}`;
}
export function MonthlyChart({ title, subtitle, points, series, currency, stacked = false }: { title: string; subtitle: string; points?: MonthlyPoint[]; series: { key: string; label: string }[]; currency?: string; stacked?: boolean }) {
  const money = useMoney(); const values = (points ?? []).flatMap(p => { const v = series.map(s => minor(p[s.key] ?? '0')); return stacked ? [v.filter(n => n > 0n).reduce((a,b) => a+b,0n),v.filter(n => n < 0n).reduce((a,b) => a+b,0n)] : v; });
  const high = values.reduce((a, b) => b > a ? b : a, 0n); const low = values.reduce((a, b) => b < a ? b : a, 0n); const span = high - low || 1n;
  const y = (value: bigint) => 200 - ratio(value - low, span) * 175;
  const slot = 480 / Math.max(1, points?.length ?? 0); const width = Math.min(stacked ? 32 : 24, slot * 0.65 / (stacked ? 1 : Math.max(1, series.length)));
  return <Card title={title} subtitle={subtitle}><div className="p-4"><div className="mb-2 flex flex-wrap gap-4 text-[11px] text-tx3">{series.map((s, i) => <span key={s.key} className="flex items-center gap-1.5"><i className="size-2" style={{ background: COLORS[i] }} />{s.label}</span>)}</div>
    {!points ? <div className="flex h-[240px] items-center justify-center text-tx3">Loading chart…</div> : <svg viewBox="0 0 540 240" role="img" aria-label={title} className="h-[240px] w-full">
      {[0, 1, 2, 3, 4].map(i => <g key={i}><line x1="42" x2="530" y1={25 + i * 43.75} y2={25 + i * 43.75} stroke="var(--bd)" strokeDasharray="2 3" /><text x="36" y={29 + i * 43.75} textAnchor="end" fill="var(--tx3)" fontSize="10">{axis(high - (high - low) * BigInt(i) / 4n)}</text></g>)}
      <line x1="42" x2="530" y1={y(0n)} y2={y(0n)} stroke="var(--bd2)" />
      {points.map((p, index) => { let positive = 0n, negative = 0n; return <g key={p.month}><text x={48 + slot * (index + .5)} y="225" textAnchor="middle" fill="var(--tx3)" fontSize="10">{new Date(`${p.month}-01T12:00:00`).toLocaleDateString('en', { month: 'short' })}</text>{series.map((s, i) => { const value = minor(p[s.key] ?? '0'); const from = stacked ? (value >= 0n ? positive : negative) : 0n; const to = from + value; if(value >= 0n) positive = to; else negative = to; return <rect key={s.key} x={48 + slot * (index + .5) + (stacked ? -.5 : i - series.length / 2) * width} y={Math.min(y(to), y(from))} width={Math.max(2, width - 2)} height={Math.max(0, Math.abs(y(to) - y(from)))} fill={COLORS[i % COLORS.length]}><title>{p.month} · {s.label} · {money(p[s.key], currency)}</title></rect>; })}</g>; })}
      {!values.some(v => v !== 0n) && <text x="285" y="115" textAnchor="middle" fill="var(--tx3)" fontSize="12">No posted activity in the selected period</text>}
    </svg>}
  </div></Card>;
}
export function BreakdownChart({ title, subtitle, rows, currency, aging = false, compact = false, emptyLabel = 'No posted expense activity.' }: { title: string; subtitle: string; rows?: Breakdown[]; currency?: string; aging?: boolean; compact?: boolean; emptyLabel?: string }) {
  const money = useMoney(); const total = (rows ?? []).reduce((sum, r) => sum + abs(minor(r.amount)), 0n);
  const peak = (rows ?? []).reduce((m,r) => abs(minor(r.amount)) > m ? abs(minor(r.amount)) : m, 0n);
  const agingColors = ['var(--c4)', 'var(--c1)', 'var(--c5)', 'var(--c6)', 'var(--err)'];
  return <Card title={title} subtitle={subtitle}><div className={`flex flex-col gap-3 p-4 ${compact?'min-h-[184px]':'min-h-[288px]'}`}>
    {rows ? rows.length ? aging ? <><div className="mb-1 flex h-3 w-full bg-sf3">{rows.map((r,i) => <div key={r.label} style={{ width: `${ratio(abs(minor(r.amount)), total) * 100}%`, background: agingColors[i] }} />)}</div><div className="grid grid-cols-2 gap-3 sm:grid-cols-5">{rows.map((r,i) => <div key={r.label}><span className="flex items-center gap-1 text-[11px] text-tx3"><i className="size-2" style={{background:agingColors[i]}}/>{r.label}</span><strong className="my-1 block text-[13px] tabular-nums">{money(r.amount,currency)}</strong><span className="text-[11px] text-tx3">{r.count} invoices</span></div>)}</div></> : rows.map(r => <div key={r.label} className="flex items-center gap-3 text-[11.5px]"><span className={compact?"w-[158px] shrink-0 truncate text-link":"w-[32%] truncate text-link"} title={r.label}>{r.label}</span><div className="flex min-w-0 flex-1 items-center gap-1"><div className="h-3.5" style={{width:`${ratio(abs(minor(r.amount)),peak)*(compact?90:75)}%`,background:compact?'var(--c1)':'var(--c2)'}}/><span className="whitespace-nowrap tabular-nums">{money(r.amount,currency)}</span></div></div>) : <div className="m-auto text-tx3">{emptyLabel}</div> : <div className="m-auto text-tx3">Loading breakdown…</div>}
  </div></Card>;
}
