"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { addPayment, type PaymentInstanceOut } from "@/lib/payments-api";

interface Props {
  instance: PaymentInstanceOut;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (updated: PaymentInstanceOut) => void;
}

function todayLocalIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function defaultAmount(instance: PaymentInstanceOut): string {
  const total = parseFloat(instance.amount);
  const paid = instance.paid_amount != null ? parseFloat(instance.paid_amount) : 0;
  const remaining = Number.isFinite(total) ? total - (Number.isFinite(paid) ? paid : 0) : 0;
  return Math.max(remaining, 0.01).toFixed(2);
}

export default function MarkPaidDialog({
  instance,
  isOpen,
  onClose,
  onConfirm,
}: Props) {
  const t = useTranslations("MarkPaidDialog");

  const [paidAmount, setPaidAmount] = useState(() => defaultAmount(instance));
  const [paidOn, setPaidOn] = useState(() => todayLocalIso());
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  if (!isOpen) return null;

  const amountValue = parseFloat(paidAmount);
  const amountValid = Number.isFinite(amountValue) && amountValue > 0;

  async function handleConfirm() {
    if (!amountValid) {
      setError(t("amountInvalid"));
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const updated = await addPayment(instance.id, amountValue, paidOn || null, notes || undefined);
      onConfirm(updated);
    } catch (err) {
      if (!mounted.current) return;
      setError(err instanceof Error ? err.message : t("saveFailed"));
      setIsSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="mark-paid-dialog-title"
        onKeyDown={(e) => e.key === "Escape" && !isSubmitting && onClose()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:bg-slate-800 dark:border-slate-700"
      >
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400">
          <CheckCircle size={22} />
        </div>

        <h2
          id="mark-paid-dialog-title"
          className="mb-4 text-lg font-semibold text-slate-800 dark:text-slate-100"
        >
          {t("title", { billName: instance.bill_name })}
        </h2>

        <div className="mb-3">
          <label
            htmlFor="paid-amount"
            className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300"
          >
            {t("amountLabel")}
          </label>
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 focus-within:border-green-500 focus-within:ring-2 focus-within:ring-green-100 dark:border-slate-600 dark:bg-slate-900/40 dark:focus-within:border-green-600">
            <input
              id="paid-amount"
              type="number"
              step="0.01"
              min="0.01"
              value={paidAmount}
              onChange={(e) => setPaidAmount(e.target.value)}
              className="flex-1 bg-transparent text-sm text-slate-800 outline-none dark:text-slate-100"
            />
            <span className="text-sm text-slate-400 dark:text-slate-500">
              {instance.currency}
            </span>
          </div>
          {instance.paid_amount != null && parseFloat(instance.paid_amount) > 0 && (
            <p className="mt-1.5 text-xs text-slate-400 dark:text-slate-500">
              {t("remainingHint", {
                amount: Math.max(
                  parseFloat(instance.amount) - parseFloat(instance.paid_amount),
                  0,
                ).toFixed(2),
                currency: instance.currency,
              })}
            </p>
          )}
        </div>

        <div className="mb-3">
          <label
            htmlFor="paid-date"
            className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300"
          >
            {t("dateLabel")}
          </label>
          <input
            id="paid-date"
            type="date"
            value={paidOn}
            max={todayLocalIso()}
            onChange={(e) => setPaidOn(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-green-500 focus:ring-2 focus:ring-green-100 dark:border-slate-600 dark:bg-slate-900/40 dark:text-slate-100 dark:focus:border-green-600"
          />
        </div>

        <div className="mb-5">
          <label
            htmlFor="paid-notes"
            className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300"
          >
            {t("notesLabel")}
          </label>
          <textarea
            id="paid-notes"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-green-500 focus:ring-2 focus:ring-green-100 dark:border-slate-600 dark:bg-slate-900/40 dark:text-slate-100 dark:focus:border-green-600"
          />
        </div>

        {error && (
          <p className="mb-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </p>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="flex-1 rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            {t("cancel")}
          </button>
          <button
            onClick={handleConfirm}
            disabled={isSubmitting || !amountValid}
            className="flex-1 rounded-xl border border-emerald-600 bg-emerald-600 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:border-emerald-700 hover:bg-emerald-700 disabled:opacity-50"
          >
            {isSubmitting ? t("confirming") : t("confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
