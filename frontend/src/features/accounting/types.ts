export interface Account {
  id: number;
  code: string;
  name: string;
  account_type: string;
  subtype: string;
  parent_id: number | null;
  normal_side: string;
  description: string;
  is_active: boolean;
  is_postable: boolean;
  currency: string;
  control: string;
}
export interface Line {
  tax_revision_id?: number | null;
  id: number;
  account_id: number;
  account_code: string;
  account_name: string;
  description: string;
  currency: string;
  debit: string;
  credit: string;
  base_debit: string;
  base_credit: string;
  exchange_rate: string;
  rate_source: string;
  valuation: string;
}
export interface Journal {
  id: string;
  number: string | null;
  status: "draft" | "pending" | "posted";
  kind: string;
  description: string;
  posting_date: string;
  journal_date: string;
  base_currency: string;
  revision: number;
  lines: Line[];
  reason: string;
  created_by_name: string;
  created_at: string;
  posted_at: string | null;
  reversal_of_id: string | null;
  reversed_by_id: string | null;
  approval_id: number | null;
  approval_status?: string | null;
  source_type: string;
}
export interface Config {
  base_currency: string;
  enabled_currencies: string[];
  fiscal_year_start_month: number;
  currency_display: string;
  number_grouping: string;
}
export interface Bank {
  id: number;
  name: string;
  kind: string;
  institution: string;
  identifier: string;
  currency: string;
  gl_account_id: number;
  is_active: boolean;
  balance: string;
  book_value: string;
}
export interface BankLine extends Line {
  date: string;
  number: string;
  source: string;
  journal_id: string;
  matched: boolean;
}
export interface Period {
  id: number;
  fiscal_year: number;
  start: string;
  end: string;
  is_closed: boolean;
  closed_by: number | null;
  closed_at: string | null;
  entry_count: number;
  revenue: string;
  expenses: string;
  closed_by_name: string;
}
export interface Year {
  id: number;
  name: string;
  start: string;
  end: string;
  is_closed: boolean;
}
export interface Rate {
  id: number;
  currency: string;
  base_currency: string;
  effective_date: string;
  value: string;
  source: string;
}
export interface TaxRevision {
  id: number;
  effective_date: string;
  percent: string;
  input_account: number;
  output_account: number;
}
export interface Tax {
  id: number;
  code: string;
  name: string;
  description: string;
  is_active: boolean;
  revisions: TaxRevision[];
}
export interface ReportRow {
  depth?: number;
  is_summary?: boolean;
  account_id: number;
  code: string;
  name: string;
  account_type: string;
  subtype: string;
  parent_id: number | null;
  debit: string;
  credit: string;
  balance: string;
  opening: string;
  movement: string;
  raw_balance: string;
  debit_balance?: string;
  credit_balance?: string;
  report_amount?: string;
}
export interface Report {
  report: string;
  from: string;
  to: string;
  base_currency: string;
  rows: ReportRow[];
  [key: string]: unknown;
}
export interface Ledger {
  account: { id: number; code: string; name: string };
  opening: string;
  debit: string;
  credit: string;
  closing: string;
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  results: {
    id: number;
    journal_id: string;
    date: string;
    number: string;
    description: string;
    source: string;
    debit: string;
    credit: string;
    balance: string;
  }[];
}
export interface Reconciliation {
  id: number;
  bank_account_id: number;
  bank_account_name: string;
  currency: string;
  reference: string;
  start: string;
  end: string;
  opening_balance: string;
  closing_balance: string;
  is_complete: boolean;
  evidence: { action: string; at: string; reason: string }[];
  summary: {
    ledger_balance: string;
    base_balance: string;
    statement_balance: string;
    outstanding_net: string;
    difference: string;
    unmatched_statement: number;
    unmatched_ledger: number;
  };
  lines: {
    id: number;
    date: string;
    description: string;
    reference: string;
    amount: string;
    match_group_id: number | null;
  }[];
  ledger: BankLine[];
}
