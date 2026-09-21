import { apiFetch } from "./api";
import type { Category } from "./categories-api";
import type { PaymentStatus } from "./payments-api";

export interface StatsSummary {
  due_total: string;
  paid_total: string;
  remaining_total: string;
  total_count: number;
  paid_count: number;
  upcoming_count: number;
  overdue_count: number;
  overdue_total: string;
}

export interface TrendPoint {
  period: string;
  paid_total: string;
  due_total: string;
}

export interface ForecastPoint {
  period: string;
  expected_total: string;
}

export interface CategoryStat {
  category: Category;
  paid_total: string;
  due_total: string;
}

export interface AttentionItem {
  instance_id: number;
  period: string;
  bill_name: string;
  due_date: string;
  amount: string;
  paid_amount: string | null;
  remaining: string;
  status: PaymentStatus;
}

export interface StatsOverview {
  month: string;
  months: number;
  currency: string;
  other_currencies: string[];
  summary: StatsSummary;
  trend: TrendPoint[];
  forecast: ForecastPoint[];
  by_category: CategoryStat[];
  attention: AttentionItem[];
}

export function fetchStatsOverview(month?: string): Promise<StatsOverview> {
  const query = month ? `?month=${encodeURIComponent(month)}` : "";
  return apiFetch<StatsOverview>(`/stats/overview${query}`);
}
