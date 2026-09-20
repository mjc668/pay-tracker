"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { PaymentInstanceOut } from "@/lib/payments-api";
import PaymentRow, { STATUS_STYLES } from "./PaymentRow";

interface Props {
  /** Displayed month in YYYY-MM form. */
  month: string;
  instances: PaymentInstanceOut[];
  /** Today as YYYY-MM-DD, used for the default selection and highlight. */
  todayStr: string;
  readOnly?: boolean;
  onMarkPaid: (instance: PaymentInstanceOut) => void;
  onDelete: (instance: PaymentInstanceOut) => void;
  onReverted: (updated: PaymentInstanceOut) => void;
}

const MAX_CHIPS = 3;

function firstDayOffset(year: number, monthIndex: number): number {
  const jsDay = new Date(year, monthIndex, 1).getDay(); // 0 = Sunday
  return jsDay === 0 ? 6 : jsDay - 1;
}

function dateKey(year: number, monthIndex: number, day: number): string {
  return `${year}-${String(monthIndex + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export default function PaymentCalendar({
  month,
  instances,
  todayStr,
  readOnly = false,
  onMarkPaid,
  onDelete,
  onReverted,
}: Props) {
  const t = useTranslations("PaymentsPage");
  const locale = useLocale();

  const [yearStr, monthStr] = month.split("-");
  const year = parseInt(yearStr, 10);
  const monthIndex = parseInt(monthStr, 10) - 1;
  const totalDays = new Date(year, monthIndex + 1, 0).getDate();
  const offset = firstDayOffset(year, monthIndex);

  const byDay = new Map<string, PaymentInstanceOut[]>();
  for (const inst of instances) {
    const list = byDay.get(inst.due_date) ?? [];
    list.push(inst);
    byDay.set(inst.due_date, list);
  }
  for (const list of byDay.values()) {
    list.sort((a, b) => a.bill_name.localeCompare(b.bill_name));
  }

  // The calendar only renders once the month's instances are loaded, so the
  // default selection can be derived synchronously on mount.
  const [selectedDay, setSelectedDay] = useState<string | null>(() => {
    if (todayStr.startsWith(month + "-")) return todayStr;
    return [...byDay.keys()].sort()[0] ?? null;
  });

  const weekdayHeaders = Array.from({ length: 7 }, (_, i) =>
    new Intl.DateTimeFormat(locale, { weekday: "short" }).format(
      new Date(2024, 0, 1 + i), // Jan 1 2024 = Monday
    ),
  );

  const formatFullDate = (key: string) =>
    new Intl.DateTimeFormat(locale, {
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(new Date(key + "T00:00:00"));

  const selectedInstances = selectedDay ? (byDay.get(selectedDay) ?? []) : [];

  return (
    <div data-testid="payment-calendar" role="group" aria-label={t("calendarLabel")}>
      <div data-testid="payment-calendar-grid" className="grid grid-cols-7 gap-1">
        {weekdayHeaders.map((wd, i) => (
          <div
            key={i}
            className="flex h-7 items-center justify-center text-xs font-medium capitalize text-slate-400 dark:text-slate-500"
          >
            {wd.slice(0, 2)}
          </div>
        ))}

        {Array.from({ length: offset }).map((_, i) => (
          <div key={`gap-${i}`} />
        ))}

        {Array.from({ length: totalDays }, (_, i) => i + 1).map((day) => {
          const key = dateKey(year, monthIndex, day);
          const dayInstances = byDay.get(key) ?? [];
          const visible = dayInstances.slice(0, MAX_CHIPS);
          const extra = dayInstances.length - visible.length;
          const isSelected = key === selectedDay;
          const isToday = key === todayStr;
          return (
            <button
              key={key}
              type="button"
              data-testid={`calendar-day-${key}`}
              aria-label={formatFullDate(key)}
              aria-pressed={isSelected}
              onClick={() => setSelectedDay(key)}
              className={`flex min-h-[76px] flex-col items-stretch gap-1 rounded-lg border p-1 text-left align-top transition-colors ${
                isSelected
                  ? "border-green-600 bg-green-50 dark:border-emerald-600 dark:bg-emerald-900/20"
                  : "border-slate-200 bg-white hover:border-green-300 hover:bg-green-50/50 dark:border-slate-700 dark:bg-slate-800 dark:hover:border-emerald-700"
              }`}
            >
              <span
                className={`self-center rounded-full px-1.5 text-xs font-semibold tabular-nums ${
                  isToday
                    ? "bg-green-700 text-white dark:bg-emerald-600"
                    : isSelected
                      ? "text-green-800 dark:text-emerald-300"
                      : "text-slate-600 dark:text-slate-300"
                }`}
              >
                {day}
              </span>
              {visible.map((inst) => (
                <span
                  key={inst.id}
                  className={`block truncate rounded px-1 py-0.5 text-[10px] font-medium leading-tight ${
                    STATUS_STYLES[inst.status] ?? ""
                  }`}
                >
                  {inst.bill_name} · {inst.amount}
                </span>
              ))}
              {extra > 0 && (
                <span className="block text-center text-[10px] font-semibold text-slate-400 dark:text-slate-500">
                  +{extra}
                </span>
              )}
            </button>
          );
        })}

        {Array.from({ length: (7 - ((offset + totalDays) % 7)) % 7 }).map((_, i) => (
          <div key={`tail-${i}`} />
        ))}
      </div>

      <div data-testid="calendar-selected-day" className="mt-5">
        {selectedDay && (
          <h3 className="mb-3 text-sm font-semibold capitalize text-slate-700 dark:text-slate-200">
            {formatFullDate(selectedDay)}
          </h3>
        )}
        {selectedInstances.length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500">
            {t("calendarEmptyDay")}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {selectedInstances.map((inst) => (
              <PaymentRow
                key={inst.id}
                instance={inst}
                readOnly={readOnly}
                onMarkPaid={onMarkPaid}
                onDelete={onDelete}
                onReverted={onReverted}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
