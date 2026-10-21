/* Response types mirroring the Django API (see /api/v1/schema/). */

export interface RoleRef {
  id: number;
  name: string;
  is_admin: boolean;
}

export interface Preferences {
  theme?: 'light' | 'dark';
  sidebar?: 'full' | 'compact';
  rows_per_page?: 10 | 25 | 50;
  landing_page?: string;
}

export interface CurrentUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  display_name: string;
  initials: string;
  role: RoleRef | null;
  permissions: string[];
  must_change_password: boolean;
  preferences: Preferences;
  last_login: string | null;
}

export interface SessionInfo {
  authenticated: boolean;
  user: CurrentUser | null;
}

export interface Page<T> {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  results: T[];
}

export interface UserRecord {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  display_name: string;
  initials: string;
  role: RoleRef | null;
  is_active: boolean;
  must_change_password: boolean;
  last_login: string | null;
  date_joined: string;
}

export interface TemporaryPasswordResult {
  user: UserRecord;
  temporary_password: string;
}

export interface Role {
  id: number;
  key: string;
  name: string;
  description: string;
  is_system: boolean;
  is_admin: boolean;
  is_active: boolean;
  permissions: string[];
  user_count: number;
}

export interface PermissionDef {
  code: string;
  label: string;
  category: string;
  category_label: string;
  description: string;
}

export interface StoredFileRef {
  id: string;
  url: string;
  original_name: string;
  width: number | null;
  height: number | null;
}

export interface CompanyProfile {
  display_name: string;
  legal_name: string;
  email: string;
  phone: string;
  website: string;
  address_line1: string;
  address_line2: string;
  city: string;
  region: string;
  postal_code: string;
  country: string;
  tax_id: string;
  registration_number: string;
  base_currency: string;
  time_zone: string;
  fiscal_year_start_month: number;
  notes: string;
  logo: StoredFileRef | null;
  created_at: string;
  updated_at: string;
}

export interface CompanySummary {
  configured: boolean;
  display_name: string | null;
  legal_name: string | null;
  initials: string | null;
  location: string | null;
  logo_url: string | null;
}

export interface BusinessSettings {
  currency_display: 'symbol' | 'code';
  number_grouping: 'international' | 'south_asian';
  enabled_currencies: string[];
  tax_registered: boolean;
  tax_label: string;
  tax_registration_label: string;
  default_tax_rate: string | null;
  prices_include_tax: boolean;
  numbering: Record<string, string>;
  updated_at: string;
}

export interface Currency {
  code: string;
  name: string;
  symbol: string;
  minor_units: number;
}

export interface ModuleInfo {
  key: string;
  label: string;
  description: string;
  phase: number;
  nav_id: string;
  enabled: boolean;
  implemented: boolean;
}

export interface ModulesResponse {
  optional: ModuleInfo[];
  core: string[];
}

export interface SealConfig {
  mode: 'editor' | 'image' | 'none';
  top: string;
  center: string;
  bottom: string;
  color: string;
  shape: 'circle' | 'square';
}

export interface BrandingConfig {
  invoice_template: 'meridian' | 'ledger' | 'atlas';
  brand_color: string;
  accent_color: string;
  header_layout: 'logo-left' | 'logo-right' | 'centered';
  typography: 'sans' | 'serif' | 'mono';
  spacing: 'compact' | 'regular' | 'airy';
  table_style: 'lined' | 'striped' | 'boxed';
  logo_size: number;
  footer_text: string;
  terms: string;
  payment_instructions: string;
  custom_fields: { label: string; value: string }[];
  signature_name: string;
  signature_title: string;
  show_signature_on_invoice: boolean;
  show_signature_on_receipt: boolean;
  receipt_template: 'official' | 'compact';
  receipt_confirmation: string;
  receipt_footer: string;
  show_logo_on_receipt: boolean;
  seal: SealConfig;
}

export interface CompanySnapshot {
  display_name: string;
  legal_name: string;
  address_lines: string[];
  email: string;
  phone: string;
  website: string;
  tax_id: string;
  registration_number: string;
  base_currency?: string;
  logo_url?: string | null;
}

export interface BrandingVersionSummary {
  number: number;
  label: string;
  invoice_template: string;
  receipt_template: string;
  brand_color: string;
  accent_color: string;
  published_by: string;
  published_at: string;
  restored_from: number | null;
  approved: boolean;
}

export interface BrandingVersionDetail extends BrandingVersionSummary {
  config: BrandingConfig;
  company: CompanySnapshot;
  numbering: { invoice: string; receipt: string };
  logo_url: string | null;
  signature_url: string | null;
  seal_image_url: string | null;
}

export interface BrandingDraft {
  config: BrandingConfig;
  signature_url: string | null;
  seal_image_url: string | null;
  updated_at: string;
  updated_by: string | null;
}

export interface ApprovalRequest {
  vote_count?: number;
  required_approvals?: number;
  id: number;
  category: string;
  action: string;
  title: string;
  status: 'pending' | 'approved' | 'rejected' | 'cancelled';
  requested_by: { id: number; display_name: string };
  requested_at: string;
  request_reason: string;
  reviewed_by: { id: number; display_name: string } | null;
  reviewed_at: string | null;
  decision_reason: string;
  result_reference: string;
  can_decide: boolean;
  summary: Record<string, string>;
}

export interface BrandingOverview {
  current: BrandingVersionDetail | null;
  draft: BrandingDraft;
  has_unpublished_changes: boolean;
  versions: BrandingVersionSummary[];
  pending_request: ApprovalRequest | null;
  approval_required: boolean;
  company: CompanySnapshot | null;
  numbering: { invoice: string; receipt: string; next_invoice: string; next_receipt: string };
  display: DocumentDisplay;
}

export interface DocumentDisplay {
  currency: string;
  symbol: string;
  currency_display: 'symbol' | 'code';
  number_grouping: 'international' | 'south_asian';
  tax_label: string;
}

export type PublishResult =
  | { status: 'published'; version: BrandingVersionDetail }
  | { status: 'pending_approval'; request: ApprovalRequest };

export interface ApprovalPolicy {
  required_approvals?: number;
  category: string;
  label: string;
  description: string;
  phase: number;
  enforced: boolean;
  supports_threshold: boolean;
  is_required: boolean;
  is_active: boolean;
  approver_role: RoleRef | null;
  amount_threshold: string | null;
  allow_self_approval: boolean;
  notes: string;
  updated_at: string;
}

export interface AuditEvent {
  id: string;
  occurred_at: string;
  actor: number | null;
  actor_label: string;
  action: string;
  category: string;
  target_type: string;
  target_id: string;
  target_label: string;
  request_id: string;
  ip_address: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  outcome: 'success' | 'failure' | 'denied';
  reason: string;
}
