"use client";

import { useTranslations, useLocale } from "next-intl";
import type { CategoryStat } from "@/lib/stats-api";

interface Props {
  categories: CategoryStat[];
  currency: string;
}

function parseAmount(value: string): number {
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export default function CategoryBars({ categories, currency }: Props) {
  const t = useTranslations("Dashboard");
  const tCategories = useTranslations("Categories");
  const locale = useLocale();

  const amountFormatter = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  if (categories.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-400 dark:border-slate-700 dark:text-slate-500">
        {t("categoryEmpty")}
      </p>
    );
  }

  const sorted = [...categories].sort((a, b) => {
    const paidDiff = parseAmount(b.paid_total) - parseAmount(a.paid_total);
    if (paidDiff !== 0) return paidDiff;
    return a.category.localeCompare(b.category);
  });

  const scale = Math.max(
    ...sorted.map((item) =>
      Math.max(parseAmount(item.paid_total), parseAmount(item.due_total)),
    ),
    0,
  );

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      {sorted.map((item) => {
        const paid = parseAmount(item.paid_total);
        const due = parseAmount(item.due_total);
        const paidPct = scale > 0 ? (paid / scale) * 100 : 0;
        const duePct = scale > 0 ? (due / scale) * 100 : 0;
        return (
          <div key={item.category}>
            <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
              <span className="font-medium text-slate-700 dark:text-slate-200">
                {tCategories(item.category)}
              </span>
              <span className="flex shrink-0 items-baseline gap-3 text-xs tabular-nums text-slate-400 dark:text-slate-500">
                <span className="text-emerald-600 dark:text-emerald-400">
                  {t("categoryPaid", {
                    amount: `${amountFormatter.format(paid)} ${currency}`,
                  })}
                </span>
                <span>
                  {t("categoryDue", {
                    amount: `${amountFormatter.format(due)} ${currency}`,
                  })}
                </span>
              </span>
            </div>
            <div className="relative h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-amber-300/70 dark:bg-amber-500/40"
                style={{ width: `${duePct}%` }}
              />
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-emerald-500"
                style={{ width: `${paidPct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
