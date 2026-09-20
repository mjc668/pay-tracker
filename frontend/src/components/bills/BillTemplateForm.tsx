"use client";

import { FormEvent, useState } from "react";
import { useTranslations, useLocale } from "next-intl";
import CategoryCombobox from "./CategoryCombobox";
import MonthDayCalendar from "./MonthDayCalendar";
import type { BillCategory, BillFrequency, BillTemplateCreate } from "@/lib/bills-api";

const PRESET_CURRENCIES = ["EUR", "PLN", "USD", "AUD"] as const;

const FREQUENCY_VALUES: BillFrequency[] = ["monthly", "every_2_months", "quarterly", "annual", "one_off"];

const RECURRING_FREQUENCIES: BillFrequency[] = ["monthly", "every_2_months", "quarterly"];

const LOCALE_DEFAULT_CURRENCY: Record<string, string> = {
  pl: "PLN",
  de: "EUR",
  en: "USD",
};

type CurrencyOption = (typeof PRESET_CURRENCIES)[number] | "custom";

interface Props {
  initial?: Partial<BillTemplateCreate>;
  onSave: (data: BillTemplateCreate) => Promise<void>;
  onCancel: () => void;
}

interface Errors {
  name?: string;
  amount?: string;
  due_day?: string;
  category?: string;
}

const inputClass =
  "w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-all focus:border-green-500 focus:ring-2 focus:ring-green-100 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-100 dark:focus:border-green-600 dark:focus:ring-green-900/40";

const labelClass = "block text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500 mb-1.5";

export default function BillTemplateForm({ initial, onSave, onCancel }: Props) {
  const t = useTranslations("BillTemplateForm");
  const locale = useLocale();
  const [name, setName] = useState(initial?.name ?? "");
  const [category, setCategory] = useState<BillCategory | "">(initial?.category ?? "");
  const [frequency, setFrequency] = useState<BillFrequency>(
    initial?.frequency ?? "monthly",
  );
  const [amount, setAmount] = useState(initial?.amount ?? "");
  const initialCurrency = initial?.currency ?? LOCALE_DEFAULT_CURRENCY[locale] ?? "EUR";
  const isPreset = (PRESET_CURRENCIES as readonly string[]).includes(initialCurrency);
  const [currencyOption, setCurrencyOption] = useState<CurrencyOption>(
    isPreset ? (initialCurrency as CurrencyOption) : "custom",
  );
  const [customCurrency, setCustomCurrency] = useState(isPreset ? "" : initialCurrency);
  const [dueDay, setDueDay] = useState(
    initial?.due_day != null ? String(initial.due_day) : String(new Date().getDate()),
  );
  const [dueMonth, setDueMonth] = useState(
    initial?.due_month != null ? String(initial.due_month) : String(new Date().getMonth() + 1),
  );
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [isPaused, setIsPaused] = useState(initial?.is_paused ?? false);
  const [errors, setErrors] = useState<Errors>({});
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const isRecurring = RECURRING_FREQUENCIES.includes(frequency);

  function validate(fields: {
    name: string;
    amount: string;
    category: BillCategory | "";
  }): Errors {
    const e: Errors = {};
    if (!fields.name.trim()) e.name = t("nameRequired");
    if (fields.amount.trim() && isNaN(Number(fields.amount.trim().replace(",", "."))))
      e.amount = t("amountInvalid");
    if (!fields.category) e.category = t("categoryRequired");
    return e;
  }

  function revalidate(overrides: Partial<{ name: string; amount: string; category: BillCategory | "" }>) {
    if (submitAttempted) {
      setErrors(validate({ name, amount, category, ...overrides }));
    }
  }

  function handleNameChange(v: string) { setName(v); revalidate({ name: v }); }
  function handleAmountChange(v: string) { setAmount(v); revalidate({ amount: v }); }
  function handleCategoryChange(v: BillCategory | "") { setCategory(v); revalidate({ category: v }); }
  function handleFrequencyChange(v: BillFrequency) { setFrequency(v); }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitAttempted(true);
    const errs = validate({ name, amount, category });
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setSaving(true);
    setApiError(null);
    try {
      const resolvedCurrency =
        currencyOption === "custom" ? customCurrency.trim().toUpperCase() : currencyOption;
      const payload: BillTemplateCreate = {
        name: name.trim(),
        category: category as BillCategory,
        frequency,
        amount: amount.trim() || "0",
        currency: resolvedCurrency || "EUR",
        due_day: dueDay ? parseInt(dueDay, 10) : null,
        due_month: dueMonth ? parseInt(dueMonth, 10) : null,
        notes: notes.trim() || null,
        is_paused: isPaused,
      };
      await onSave(payload);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : t("saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      {apiError && (
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
          {apiError}
        </div>
      )}

      {/* Row 1: Name + Amount */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="bill-name" className={labelClass}>
            {t("nameLabel")} <span className="text-red-400">*</span>
          </label>
          <input
            id="bill-name"
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder={t("namePlaceholder")}
            className={inputClass}
          />
          {errors.name && <p className="mt-1 text-xs text-red-500">{errors.name}</p>}
        </div>

        <div>
          <label htmlFor="bill-amount" className={labelClass}>{t("amountLabel")}</label>
          <div className="flex gap-2">
            <input
              id="bill-amount"
              value={amount}
              onChange={(e) => handleAmountChange(e.target.value)}
              placeholder="0.00"
              inputMode="decimal"
              className={inputClass}
            />
            <select
              aria-label={t("currencyAriaLabel")}
              value={currencyOption}
              onChange={(e) => setCurrencyOption(e.target.value as CurrencyOption)}
              className="w-28 shrink-0 rounded-xl border border-slate-200 bg-white px-2 py-2.5 text-sm text-slate-800 outline-none transition-all focus:border-green-500 focus:ring-2 focus:ring-green-100 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-100 dark:focus:border-green-600 dark:focus:ring-green-900/40"
            >
              {PRESET_CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
              <option value="custom">{t("customOption")}</option>
            </select>
          </div>
          {currencyOption === "custom" && (
            <input
              aria-label={t("customCurrencyAriaLabel")}
              value={customCurrency}
              onChange={(e) => setCustomCurrency(e.target.value)}
              placeholder={t("customCurrencyPlaceholder")}
              maxLength={10}
              className={inputClass + " mt-2"}
            />
          )}
          {errors.amount && <p className="mt-1 text-xs text-red-500">{errors.amount}</p>}
        </div>
      </div>

      {/* Row 2: Frequency pills */}
      <div>
        <label className={labelClass}>
          {t("frequencyLabel")} <span className="text-red-400">*</span>
        </label>
        <div className="flex flex-wrap gap-2">
          {FREQUENCY_VALUES.map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => handleFrequencyChange(v)}
              className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-all ${
                frequency === v
                  ? "border-green-600 bg-green-50 text-green-700 shadow-sm dark:border-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400"
                  : "border-slate-200 bg-white text-slate-600 hover:border-green-300 hover:bg-green-50 hover:text-green-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-emerald-700 dark:hover:text-emerald-400"
              }`}
            >
              {t(`frequency.${v}` as never)}
            </button>
          ))}
        </div>
      </div>

      {/* Row 3: Date picker (calendar for all frequencies) */}
      <div>
        <label className={labelClass}>
          {isRecurring ? t("startDateLabel") : t("dueDateLabel")}
        </label>
        <MonthDayCalendar
          month={parseInt(dueMonth, 10) || new Date().getMonth() + 1}
          day={parseInt(dueDay, 10) || new Date().getDate()}
          onChange={(m, d) => { setDueMonth(String(m)); setDueDay(String(d)); }}
        />
      </div>

      {/* Row 4: Category + Notes */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="bill-category" className={labelClass}>{t("categoryLabel")}</label>
          <CategoryCombobox
            id="bill-category"
            value={category}
            onChange={handleCategoryChange}
          />
          {errors.category && <p className="mt-1 text-xs text-red-500">{errors.category}</p>}
        </div>
        <div>
          <label htmlFor="bill-notes" className={labelClass}>{t("notesLabel")}</label>
          <textarea
            id="bill-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder={t("notesPlaceholder")}
            className={inputClass + " resize-none"}
          />
        </div>
      </div>

      {/* Paused toggle */}
      <label className="flex cursor-pointer items-center gap-2.5 text-sm text-slate-600 dark:text-slate-400">
        <input
          type="checkbox"
          checked={isPaused}
          onChange={(e) => setIsPaused(e.target.checked)}
          className="h-4 w-4 rounded accent-green-700"
        />
        {t("pauseRecurrence")}
      </label>

      <div className="flex justify-end gap-3 border-t border-slate-100 pt-4 dark:border-slate-700">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
        >
          {t("cancel")}
        </button>
        <button
          type="submit"
          disabled={saving}
          className="rounded-xl border border-green-700 bg-green-700 px-5 py-2 text-sm font-medium text-white shadow-sm transition-all hover:border-green-800 hover:bg-green-800 disabled:opacity-50"
        >
          {saving ? t("saving") : t("save")}
        </button>
      </div>
    </form>
  );
}
