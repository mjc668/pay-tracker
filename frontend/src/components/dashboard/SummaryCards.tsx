"use client";

import { AlertCircle, CalendarClock, CheckCircle2, Wallet } from "lucide-react";
import { useTranslations, useLocale } from "next-intl";
import type { StatsSummary } from "@/lib/stats-api";

interface Props {
  summary: StatsSummary;
  currency: string;
}

interface CardConfig {
  key: "due" | "paid" | "remaining" | "overdue";
  label: string;
  amount: string;
  count: number;
  accent: string;
  iconClass: string;
  Icon: typeof CalendarClock;
}

function parseAmount(value: string): number {
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export default function SummaryCards({ summary, currency }: Props) {
  const t = useTranslations("Dashboard");
  const locale = useLocale();

  const amountFormatter = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const cards: CardConfig[] = [
    {
      key: "due",
      label: t("cardDue"),
      amount: summary.due_total,
      count: summary.total_count,
      accent: "border-l-blue-400 dark:border-l-blue-500",
      iconClass: "bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-400",
      Icon: CalendarClock,
    },
    {
      key: "paid",
      label: t("cardPaid"),
      amount: summary.paid_total,
      count: summary.paid_count,
      accent: "border-l-emerald-400 dark:border-l-emerald-500",
      iconClass: "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-400",
      Icon: CheckCircle2,
    },
    {
      key: "remaining",
      label: t("cardRemaining"),
      amount: summary.remaining_total,
      count: Math.max(summary.total_count - summary.paid_count, 0),
      accent: "border-l-amber-400 dark:border-l-amber-500",
      iconClass: "bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400",
      Icon: Wallet,
    },
    {
      key: "overdue",
      label: t("cardOverdue"),
      amount: summary.overdue_total,
      count: summary.overdue_count,
      accent: "border-l-red-400 dark:border-l-red-500",
      iconClass: "bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400",
      Icon: AlertCircle,
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map(({ key, label, amount, count, accent, iconClass, Icon }) => (
        <div
          key={key}
          data-testid={`summary-${key}`}
          className={`rounded-xl border border-slate-200 border-l-4 ${accent} bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800`}
        >
          <div className="flex items-center gap-3">
            <div className={`rounded-lg p-2 ${iconClass}`}>
              <Icon size={18} />
            </div>
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
              {label}
            </p>
          </div>
          <p className="mt-3 text-xl font-semibold tabular-nums text-slate-800 dark:text-slate-100">
            {amountFormatter.format(parseAmount(amount))}{" "}
            <span className="text-sm font-medium text-slate-400 dark:text-slate-500">
              {currency}
            </span>
          </p>
          <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
            {t("cardCount", { count })}
          </p>
        </div>
      ))}
    </div>
  );
}
