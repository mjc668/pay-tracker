"use client";

import { useEffect, useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { deletePayment, type PaymentInstanceOut } from "@/lib/payments-api";
import { normalizeBillFrequency } from "@/lib/bills-api";

interface Props {
  instance: PaymentInstanceOut;
  isOpen: boolean;
  onClose: () => void;
  onDeleted: (id: number) => void;
}

export default function DeletePaymentDialog({
  instance,
  isOpen,
  onClose,
  onDeleted,
}: Props) {
  const t = useTranslations("DeletePaymentDialog");
  const tFreq = useTranslations("Frequencies");
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteFuture, setDeleteFuture] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  if (!isOpen) return null;

  const frequency = normalizeBillFrequency(instance.frequency);
  const isRecurring = frequency !== "one_off";
  const frequencyLabel = tFreq(frequency, {
    count: instance.interval_count ?? 1,
  });

  async function handleConfirm() {
    setIsDeleting(true);
    setError(null);
    try {
      await deletePayment(instance.id, deleteFuture);
      if (mounted.current) onDeleted(instance.id);
    } catch (err) {
      if (!mounted.current) return;
      setError(err instanceof Error ? err.message : t("deleteFailed"));
      setIsDeleting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-payment-dialog-title"
        onKeyDown={(e) => e.key === "Escape" && !isDeleting && onClose()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:bg-slate-800 dark:border-slate-700"
      >
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400">
          <Trash2 size={22} />
        </div>

        <h2
          id="delete-payment-dialog-title"
          className="mb-1 text-lg font-semibold text-slate-800 dark:text-slate-100"
        >
          {t("title")}
        </h2>

        <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-300">
          {instance.bill_name}
          <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500 dark:bg-slate-700 dark:text-slate-400">
            {frequencyLabel}
          </span>
        </p>

        <p className="mb-5 text-sm text-slate-500 dark:text-slate-400">
          {isRecurring
            ? t("descriptionRecurring")
            : t("descriptionOneOff")}
        </p>

        {isRecurring && (
          <label className="mb-5 flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={deleteFuture}
              onChange={(e) => setDeleteFuture(e.target.checked)}
              disabled={isDeleting}
              className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded border-slate-300 accent-red-600 disabled:opacity-50"
            />
            <span className="text-sm text-slate-600 dark:text-slate-400">
              {t("deleteFutureLabel")}
            </span>
          </label>
        )}

        {error && (
          <p className="mb-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </p>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            disabled={isDeleting}
            className="flex-1 rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            {t("cancel")}
          </button>
          <button
            onClick={handleConfirm}
            disabled={isDeleting}
            className="flex-1 rounded-xl border border-red-600 bg-red-600 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:border-red-700 hover:bg-red-700 disabled:opacity-50"
          >
            {isDeleting ? t("deleting") : t("confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
