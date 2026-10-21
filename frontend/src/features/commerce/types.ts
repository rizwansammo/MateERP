/* API shapes for Sales & Billing, Purchases and Documents. Amounts are exact decimal strings. */

import type { DocumentSnapshot, ReceiptSnapshot } from '@/features/documents/view';
import type { CompanySnapshot } from '@/lib/api/types';

export interface JournalRef {
  id: string;
  number: string;
}

export interface Contact {
  id: number;
  name: string;
  role: string;
  email: string;
  phone: string;
  is_primary: boolean;
  is_active: boolean;
}

export type Balances = Record<string, { outstanding: string; overdue: string; credit?: string }>;

export interface Customer {
  id: number;
  code: string;
  name: string;
  contact_name: string;
  email: string;
  phone: string;
  tax_id: string;
  address: string;
  city: string;
  country: string;
  currency: string;
  payment_terms_days: number;
  notes: string;
  is_active: boolean;
  created_at: string;
  contacts?: Contact[];
  balances?: Balances;
}

export interface Milestone {
  id: number;
  position: number;
  name: string;
  percent: string;
  amount: string;
}

export interface Project {
  id: number;
  reference: string;
  name: string;
  customer_id: number;
  customer_name: string;
  currency: string;
  contract_value: string;
  status: 'active' | 'on_hold' | 'completed' | 'cancelled';
  notes: string;
  milestones: Milestone[];
}

export interface BillingItem {
  id: number;
  code: string;
  name: string;
  description: string;
  unit: string;
  unit_price: string;
  currency: string;
  revenue_account_id: number | null;
  tax_code_id: number | null;
  is_active: boolean;
}

export interface DocLine {
  id?: number;
  position?: number;
  item_id?: number | null;
  sales_order_line_id?: number | null;
  description: string;
  quantity: string;
  unit_price: string;
  discount_type: 'percent' | 'fixed';
  discount_value: string;
  tax_code_id: number | null;
  revenue_account_id?: number | null;
  account_id?: number | null;
  invoiced_quantity?: string;
  subtotal?: string;
  line_discount?: string;
  document_discount?: string;
  taxable?: string;
  tax?: string;
  total?: string;
  tax_rate?: string;
  credited_taxable?: string;
  credited_tax?: string;
}

export interface SalesOrder {
  id: number;
  number: string;
  customer_id: number;
  customer_name: string;
  project_id: number | null;
  order_date: string;
  currency: string;
  title: string;
  customer_reference: string;
  prices_include_tax: boolean;
  tax: string;
  total: string;
  status: 'draft' | 'confirmed' | 'partially_invoiced' | 'invoiced' | 'cancelled';
  notes: string;
  revision: number;
  created_at: string;
  confirmed_at: string | null;
  cancelled_reason: string;
  lines: DocLine[];
}

export type InvoiceStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'issued'
  | 'partially_paid'
  | 'paid'
  | 'credited'
  | 'void'
  | 'cancelled';

export interface InvoiceRow {
  id: number;
  number: string | null;
  status: InvoiceStatus;
  customer_id: number;
  customer_name: string;
  project_reference: string | null;
  issue_date: string;
  due_date: string;
  currency: string;
  total: string;
  amount_paid: string;
  amount_credited: string;
  outstanding: string;
  is_overdue: boolean;
  pdf_status: 'none' | 'pending' | 'ready' | 'failed';
  pdf_url: string | null;
  created_at: string;
}

export interface InvoiceSnapshot extends DocumentSnapshot {
  number: string;
  customer: Record<string, string>;
  company: CompanySnapshot;
  taxes: { code: string; rate: string; taxable: string; tax: string }[];
  totals: Record<string, string>;
  format: { currency: string; symbol: string; display: 'symbol' | 'code'; grouping: 'international' | 'south_asian' };
  exchange_rate: string;
  base_currency: string;
  base_total: string;
  [key: string]: unknown;
}

export interface Invoice extends InvoiceRow {
  project_id: number | null;
  milestone_id: number | null;
  sales_order_id: number | null;
  prices_include_tax: boolean;
  discount_type: 'percent' | 'fixed';
  discount_value: string;
  reference: string;
  notes: string;
  subtotal: string;
  line_discount: string;
  document_discount: string;
  taxable: string;
  tax: string;
  exchange_rate: string | null;
  base_total: string | null;
  revision: number;
  lines: DocLine[];
  journal: JournalRef | null;
  void_journal: JournalRef | null;
  void_reason: string;
  approval_id: number | null;
  branding_version: number | null;
  snapshot: InvoiceSnapshot | Record<string, never>;
  created_by: string;
  approved_by: string | null;
  approved_at: string | null;
  issued_by: string | null;
  issued_at: string | null;
  pdf_error: string;
  allocations: { payment_id: number; number: string; date: string; status: string; amount: string }[];
  credit_notes: { id: number; number: string | null; status: string; total: string; date: string }[];
}

export interface Allocation {
  invoice_id: number;
  invoice_number: string;
  amount: string;
  base_amount: string | null;
}

export type PaymentStatus =
  | 'pending_verification'
  | 'awaiting_approval'
  | 'verified'
  | 'rejected'
  | 'cancelled'
  | 'reversed';

export interface Payment {
  id: number;
  number: string;
  status: PaymentStatus;
  customer_id: number;
  customer_name: string;
  bank_account_id: number;
  bank_account_name: string;
  payment_date: string;
  currency: string;
  amount: string;
  unapplied_amount: string;
  method: string;
  reference: string;
  notes: string;
  recorded_by: string;
  recorded_by_id: number;
  recorded_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_reason: string;
  approval_id: number | null;
  exchange_rate: string | null;
  base_amount: string | null;
  allocations: Allocation[];
  journal: JournalRef | null;
  reversal_journal: JournalRef | null;
  receipt: { id: number; number: string; status: string } | null;
}

export interface Receipt {
  id: number;
  number: string;
  status: 'issued' | 'cancelled';
  issue_date: string;
  payment_id: number;
  payment_number: string;
  customer_name: string;
  amount: string;
  currency: string;
  branding_version: number;
  snapshot: ReceiptSnapshot & { company: CompanySnapshot };
  pdf_status: 'none' | 'pending' | 'ready' | 'failed';
  pdf_url: string | null;
  pdf_error: string;
}

export interface CreditNote {
  id: number;
  number: string | null;
  status: 'awaiting_approval' | 'issued' | 'rejected';
  invoice_id: number;
  invoice_number: string;
  customer_id: number;
  customer_name: string;
  issue_date: string;
  reason: string;
  currency: string;
  taxable: string;
  tax: string;
  total: string;
  applied_amount: string;
  credit_amount: string;
  approval_id: number | null;
  journal: JournalRef | null;
  pdf_status: 'none' | 'pending' | 'ready' | 'failed';
  pdf_url: string | null;
  pdf_error: string;
}

export interface Refund {
  id: number;
  number: string;
  status: 'awaiting_approval' | 'paid' | 'rejected';
  customer_id: number;
  customer_name: string;
  bank_account_id: number;
  bank_account_name: string;
  refund_date: string;
  currency: string;
  amount: string;
  method: string;
  reference: string;
  reason: string;
  approval_id: number | null;
  journal: JournalRef | null;
}

export interface Run {
  id: number;
  occurrence_date: string;
  status: 'drafted' | 'issued' | 'failed';
  message: string;
  invoice_id?: number | null;
  invoice_number?: string | null;
  expense_id?: number | null;
  expense_number?: string | null;
  created_at: string;
}

export interface Schedule {
  id: number;
  name: string;
  customer_id: number;
  customer_name: string;
  project_id: number | null;
  currency: string;
  frequency: 'weekly' | 'monthly' | 'quarterly' | 'yearly';
  interval: number;
  start_date: string;
  end_date: string | null;
  next_run_date: string | null;
  due_days: number;
  template: { lines: DocLine[]; notes?: string; reference?: string; prices_include_tax?: boolean };
  auto_issue: boolean;
  auto_issue_authorized_by: string | null;
  status: 'active' | 'paused' | 'cancelled' | 'completed';
  revision: number;
  created_at: string;
  runs?: Run[];
  due?: string[];
}

export interface Calculation {
  currency: string;
  prices_include_tax: boolean;
  lines: Record<string, string | number | null>[];
  taxes: { tax_revision_id: number; code: string; rate: string; taxable: string; tax: string }[];
  subtotal: string;
  line_discount: string;
  document_discount: string;
  taxable: string;
  tax: string;
  total: string;
}

export interface Vendor {
  id: number;
  code: string;
  name: string;
  contact_name: string;
  email: string;
  phone: string;
  address: string;
  country: string;
  currency: string;
  payment_terms_days: number;
  tax_id: string;
  website: string;
  default_account_id: number | null;
  notes: string;
  is_active: boolean;
  created_at: string;
  balances?: Record<string, string>;
  spend?: string;
}

export type PayableStatus =
  | 'draft'
  | 'awaiting_approval'
  | 'posted'
  | 'partially_paid'
  | 'paid'
  | 'void'
  | 'cancelled';

export interface Bill {
  id: number;
  number: string | null;
  status: PayableStatus;
  vendor_id: number;
  vendor_name: string;
  vendor_reference: string;
  project_id: number | null;
  bill_date: string;
  due_date: string;
  currency: string;
  prices_include_tax: boolean;
  notes: string;
  subtotal: string;
  line_discount: string;
  taxable: string;
  tax: string;
  total: string;
  amount_paid: string;
  outstanding: string;
  exchange_rate: string | null;
  base_total: string | null;
  revision: number;
  approval_id: number | null;
  journal: JournalRef | null;
  void_journal: JournalRef | null;
  void_reason: string;
  created_by: string;
  created_at: string;
  posted_at: string | null;
  lines: DocLine[];
}

export interface Expense {
  id: number;
  number: string | null;
  status: PayableStatus;
  vendor_id: number | null;
  vendor_name: string | null;
  project_id: number | null;
  expense_date: string;
  original_transaction_date?: string | null;
  recognition_reason?: string;
  due_date: string | null;
  description: string;
  currency: string;
  account_id: number;
  account_name: string;
  entered_amount: string;
  prices_include_tax: boolean;
  tax_code_id: number | null;
  taxable: string;
  tax: string;
  total: string;
  payment_mode: 'paid' | 'accrued';
  bank_account_id: number | null;
  bank_account_name: string | null;
  method: string;
  reference: string;
  notes: string;
  amount_paid: string;
  outstanding: string;
  exchange_rate: string | null;
  base_total: string | null;
  revision: number;
  approval_id: number | null;
  journal: JournalRef | null;
  void_journal: JournalRef | null;
  void_reason: string;
  created_by: string;
  created_at: string;
  recurring_schedule_id: number | null;
}

export interface VendorPayment {
  id: number;
  number: string;
  status: 'awaiting_approval' | 'paid' | 'rejected' | 'reversed';
  vendor_id: number;
  vendor_name: string;
  bank_account_id: number;
  bank_account_name: string;
  payment_date: string;
  currency: string;
  amount: string;
  base_amount: string | null;
  method: string;
  reference: string;
  notes: string;
  approval_id: number | null;
  allocations: { bill_id: number | null; expense_id: number | null; document: string; amount: string; base_amount: string | null }[];
  journal: JournalRef | null;
  reversal_journal: JournalRef | null;
  created_by: string;
  created_at: string;
}

export interface ExpenseSchedule {
  id: number;
  name: string;
  vendor_id: number;
  vendor_name: string;
  currency: string;
  frequency: 'weekly' | 'monthly' | 'quarterly' | 'yearly';
  interval: number;
  start_date: string;
  end_date: string | null;
  next_run_date: string | null;
  reminder_days: number;
  template: Record<string, string | boolean | number | null>;
  status: 'active' | 'paused' | 'cancelled' | 'completed';
  revision: number;
  created_at: string;
  runs?: Run[];
  due?: string[];
}

export type DocumentKind =
  | 'invoice'
  | 'receipt'
  | 'credit_note'
  | 'bank_proof'
  | 'client_supporting'
  | 'vendor_invoice'
  | 'vendor_receipt'
  | 'vendor_supporting';

export interface FiledDocument {
  id: number;
  area: 'client' | 'vendor';
  kind: DocumentKind;
  title: string;
  document_date: string;
  generated: boolean;
  restricted: boolean;
  customer_id: number | null;
  customer_name: string | null;
  vendor_id: number | null;
  vendor_name: string | null;
  invoice_id: number | null;
  invoice_number: string | null;
  payment_id: number | null;
  payment_number: string | null;
  receipt_id: number | null;
  credit_note_id: number | null;
  vendor_bill_id: number | null;
  bill_number: string | null;
  expense_id: number | null;
  expense_number: string | null;
  vendor_payment_id: number | null;
  notes: string;
  is_archived: boolean;
  archived_reason: string;
  archived_at: string | null;
  uploaded_by: string | null;
  created_at: string;
  content_type: string;
  size: number;
  file_name: string;
  sha256: string;
  url: string;
  download_url: string;
}

export interface ClientTreeYear {
  year: number;
  count: number;
  clients: {
    id: number;
    name: string;
    count: number;
    invoices: { id: number; number: string; count: number; kinds: Partial<Record<DocumentKind, number>> }[];
    other: Partial<Record<DocumentKind, number>>;
  }[];
}

export interface VendorTreeYear {
  year: number;
  count: number;
  months: {
    month: number;
    count: number;
    vendors: { id: number; name: string; count: number; kinds: Partial<Record<DocumentKind, number>> }[];
  }[];
}

export interface Reconciled {
  account: { id: number; code: string; name: string } | null;
  subledger: string;
  ledger: string;
  difference: string;
}
