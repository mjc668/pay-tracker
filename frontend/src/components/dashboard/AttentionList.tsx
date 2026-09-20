"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useTranslations, useLocale } from "next-intl";
import type { AttentionItem } from "@/lib/stats-api";

interface Props {
  items: AttentionItem[];
  currency: string;
}

const STATUS_STYLES: Record<string, string> = {
  upcoming: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  overdue: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  paid: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
};

function parseAmount(value: string | null): number {
  if (value == null) return 0;
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export default function AttentionList({ items, currency }: Props) {
  const t = useTranslations("Dashboard");
  const tRow = useTranslations("PaymentRow");
  const locale = useLocale();

  const amountFormatter = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const formatDate = (value: string): string => {
    const label = new Intl.DateTimeFormat(locale, {
      day: "numeric",
      month: "short",
    }).format(new Date(`${value}T00:00:00`));
    return label;
  };

  if (items.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-400 dark:border-slate-700 dark:text-slate-500">
        {t("attentionEmpty")}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {items.map((item) => {
        const paid = parseAmount(item.paid_amount);
        const remaining = parseAmount(item.remaining);
        return (
          <Link
            key={item.instance_id}
            href={`/dashboard/payments?month=${item.period}`}
            className={`group flex items-center gap-3 rounded-xl border border-slate-200 border-l-4 bg-white p-4 shadow-sm transition-all hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700/50 ${
              item.status === "overdue"
                ? "border-l-red-400 dark:border-l-red-500"
                : "border-l-blue-400 dark:border-l-blue-500"
            }`}
          >
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate font-semibold text-slate-800 dark:text-slate-100">
                  {item.bill_name}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[item.status] ?? ""}`}
                >
                  {tRow(`status.${item.status}` as Parameters<typeof tRow>[0])}
                </span>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-500 dark:text-slate-400">
                <span>
                  {t("attentionDue", { date: formatDate(item.due_date) })}
                </span>
                {paid > 0 && (
                  <>
                    <span className="text-slate-300 dark:text-slate-600">•</span>
                    <span>
                      {t("attentionPaid", {
                        amount: `${amountFormatter.format(paid)} ${currency}`,
                      })}
                    </span>
                    <span className="text-slate-300 dark:text-slate-600">•</span>
                    <span>
                      {t("attentionRemaining", {
                        amount: `${amountFormatter.format(remaining)} ${currency}`,
                      })}
                    </span>
                  </>
                )}
              </div>
            </div>
            <div className="shrink-0 text-right">
              <p className="font-semibold tabular-nums text-slate-800 dark:text-slate-100">
                {amountFormatter.format(paid > 0 ? remaining : parseAmount(item.amount))}{" "}
                <span className="text-xs font-medium text-slate-400 dark:text-slate-500">
                  {currency}
                </span>
              </p>
            </div>
            <ChevronRight
              size={16}
              className="shrink-0 text-slate-300 transition-transform group-hover:translate-x-0.5 dark:text-slate-600"
            />
          </Link>
        );
      })}
    </div>
  );
}
