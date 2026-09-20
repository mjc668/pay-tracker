import { apiFetch } from "./api";
import { CATEGORY_ORDER } from "./categories";

export type BillFrequency = "monthly" | "every_2_months" | "quarterly" | "annual" | "one_off";

export type BillCategory = (typeof CATEGORY_ORDER)[number];

export interface BillTemplateOut {
  id: number;
  name: string;
  category: BillCategory;
  frequency: BillFrequency;
  amount: string;
  currency: string;
  due_day: number | null;
  due_month: number | null;
  start_period: string | null;
  notes: string | null;
  is_archived: boolean;
  is_paused: boolean;
  created_at: string;
}

export interface BillTemplateCreate {
  name: string;
  category: BillCategory;
  frequency: BillFrequency;
  amount: string;
  currency?: string;
  due_day?: number | null;
  due_month?: number | null;
  notes?: string | null;
  is_paused?: boolean;
}

export type BillTemplateUpdate = Partial<BillTemplateCreate> & {
  recreate_deleted_future?: boolean;
};

export function fetchBills(includeArchived = false): Promise<BillTemplateOut[]> {
  const qs = includeArchived ? "?include_archived=true" : "";
  return apiFetch<BillTemplateOut[]>(`/bills${qs}`);
}

export function createBill(data: BillTemplateCreate): Promise<BillTemplateOut> {
  return apiFetch<BillTemplateOut>("/bills", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateBill(
  id: number,
  data: BillTemplateUpdate,
): Promise<BillTemplateOut> {
  return apiFetch<BillTemplateOut>(`/bills/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function archiveBill(id: number): Promise<void> {
  return apiFetch<void>(`/bills/${id}/archive`, { method: "POST" });
}

export function hasDeletedFuture(id: number): Promise<{ has_deleted_future: boolean }> {
  return apiFetch<{ has_deleted_future: boolean }>(`/bills/${id}/has-deleted-future`);
}

export interface GenerateInstancesResponse {
  created: number;
  bill_count: number;
  months: number;
}

export function generateInstances(
  months: number,
  billIds?: number[],
): Promise<GenerateInstancesResponse> {
  return apiFetch<GenerateInstancesResponse>("/bills/generate-instances", {
    method: "POST",
    body: JSON.stringify({ months, bill_ids: billIds ?? null }),
  });
}
