export interface Party {
  id: number; name: string; display_name: string; kind: 'individual' | 'organization'; email: string; phone: string; country: string; notes: string;
  user: number | null; is_founder: boolean; is_shareholder: boolean; is_partner: boolean; is_active: boolean; joined: string; left: string | null;
}
export interface CorporateTransaction {
  id: number; kind: string; party: number; party_name: string; recipient: number | null; classification: string; date: string; currency: string; amount: string; base_amount: string | null;
  bank: number | null; loan: number | null; expense: number | null; issuance: number | null; reference: string; notes: string; status: string;
  created_by: number; verified_by: number | null; journal: string | null; approval: number | null; snapshot: { quote?: FinancialQuote };
}
export interface FinancialQuote { quote_fingerprint: string; fx_difference: string; base_currency: string; lines: {account_id: number; currency: string; debit: string; credit: string; base_debit: string; base_credit: string; rate_source: string}[] }
export interface Obligation { id: number; party_id: number; party: string; category: string; currency: string; amount: string; base_amount: string; outstanding: string; base_outstanding: string; origin_id: number; expense_id: number | null }
export interface Loan { id: number; party: number; name: string; currency: string; terms: string; maturity: string | null; reference: string; is_active: boolean }
export interface Policy { id: number; name: string; effective_from: string; effective_until: string | null; category: number | null; basis: string; weights: Record<string, string>; status: string; approval: number | null }
export interface SharedExpense { id: number; expense: number | null; founder_payment: number | null; payer: number; date: string; currency: string; amount: string; description: string; policy: number; snapshot: { weights: Record<string, string>; amounts: Record<string,string>; policy: string; basis: string; personal_only: boolean } }
export interface PersonalObligation { id: number; sharing_id: number; debtor_id: number; creditor_id: number; debtor: string; creditor: string; currency: string; date: string; description: string; amount: string; settled: string; outstanding: string }
export interface Settlement { id: number; payer: number; recipient: number; payer_name: string; recipient_name: string; date: string; currency: string; amount: string; reference: string; notes: string; status: string; is_return: boolean; returns: number | null; confirmations: {party_id: number; actor_id: number; mode: string; reference: string}[]; allocations: {obligation_id: number; amount: string}[] }
export interface ForecastRow { month: string; currency: string; cost: string; cash_due: string; reserve_target: string; reserve_coverage: string; funding_target: string; founder_request: string; founders: Record<string,string>; estimated_base_cost: string | null; estimated_rate?: string; rate_source?: string; sources: {identity: string; name: string; state: string; date: string; cost: string}[]; verified_designated?: string; remaining?: string; company_coverage?:string; remaining_founder_targets?:Record<string,string>; verified_by_founder?:Record<string,string>; remaining_by_founder?:Record<string,string>; surplus_by_founder?:Record<string,string> }
export interface Forecast { starts: string; months: number; base_currency: string; rows: ForecastRow[]; issues: {source: string; message: string}[]; complete: boolean }
export interface FundingPlan { id: number; name: string; starts: string; months: number; mode: string; snapshot: Forecast; previous: number | null; created_at: string }
export interface Reserve { id: number; name: string; schedule: number; starts: string; renewal: string; currency: string; target: string; status: string; progress: {designated: string; usable: string; consumed: string; released?:string; shortfall: string; cash_shortfall: string} }
export interface Designation { id: number; receipt: number; plan: number | null; reserve: number | null; month: string; amount: string; consumed_by: number | null; remaining:string; consumptions:{id:number;expense_id:number;amount:string}[] }
export interface Pledge { id: number; plan: number; party: number; month: string; currency: string; amount: string; status: string; reference: string }
export interface Reconciliation { category: string; source_balance: string; gl_balance: string; difference: string }
export interface FounderOverview { founders: {id: number; name: string; is_active: boolean; obligations: Obligation[]; events: {id:number; kind:string; classification:string; date:string; currency:string; amount:string; status:string; journal_id:string|null; journal_number:string|null}[]}[]; reconciliation: Reconciliation[]; monthly:{month:string;receipts:string;funded_costs:string;repayments:string}[] }
export interface StoredEvidence {id: number; title: string; party: number | null; file: {id: string; url: string; content_type: string; original_name: string; size: number} }
export interface CompanyCoverage {id:number;plan:number;bank:number;month:string;amount:string;currency:string;status:string;expense:number|null;reference:string}
export interface PostedCost {identity:string;name:string;journal_id:string;actual_rate:string;actual_base_cost:string;estimated_base_cost:string|null;base_cost_variance:string|null}
export interface FundingProgressRow extends ForecastRow {base_currency:string;posted_costs:PostedCost[]}
