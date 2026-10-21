import type { BillingItem } from '@/features/commerce/types';

export interface Reference {
  id: number;
  code: string;
  name: string;
  is_active: boolean;
  allows_fraction?: boolean;
  address?: string;
}
export interface CatalogItem extends BillingItem {
  profile: {
    kind: 'stock' | 'nonstock' | 'service';
    unit_id: number;
    category_id: number | null;
    purchase_account_id: number | null;
    cogs_account_id: number | null;
    inventory_account_id: number | null;
    preferred_vendor_id: number | null;
    reorder_level: string;
    revision: number;
  } | null;
}
export interface PriceRevision {
  id: number;
  purpose: 'sale' | 'purchase';
  effective_date: string;
  currency: string;
  value: string;
  includes_tax: boolean;
  reason: string;
  created_at: string;
}
export interface PurchaseOrderLine {
  id: number;
  position: number;
  item_id: number;
  item_name: string;
  description: string;
  quantity: string;
  unit_price: string;
  tax_code_id: number | null;
  taxable: string;
  tax: string;
  total: string;
  received_quantity: string;
}
export interface PurchaseOrder {
  id: number;
  number: string;
  vendor_id: number;
  vendor_name: string;
  date: string;
  expected_date: string | null;
  currency: string;
  prices_include_tax: boolean;
  notes: string;
  status: string;
  revision: number;
  total: string;
  taxable: string;
  tax: string;
  lines: PurchaseOrderLine[];
  approval_id: number | null;
}
export interface GoodsReceipt {
  id: number;
  order_line_id: number;
  order_number: string;
  item_name: string;
  date: string;
  quantity: string;
  rejected_quantity: string;
  kind: string;
  location_id: number | null;
  reference: string;
  reason: string;
  native_value: string;
  base_value: string;
  movement_id: string | null;
}
export interface StockMovement {
  id: string;
  sequence: number;
  item_id: number;
  item_code: string;
  item_name: string;
  location_id: number;
  location_name: string;
  date: string;
  kind: string;
  quantity: string;
  base_value: string;
  reason: string;
  source_type: string;
  source_id: string;
  journal_id: string | null;
}
export interface Valuation {
  reconciliation: { currency: string; stock_value: string; gl_value: string; difference: string };
}
export interface StockItem {
  id: number;
  item_id: number;
  code: string;
  name: string;
  unit: string;
  reorder_level: string;
  quantity: string;
  value: string;
  average_cost: string;
}
