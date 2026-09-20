"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import { CalendarPlus } from "lucide-react";
import { useTranslations } from "next-intl";
import { generateInstances, type BillTemplateOut } from "@/lib/bills-api";

interface Props {
  templates: BillTemplateOut[];
  onClose: () => void;
  onGenerated: () => void;
}

const inputClass =
  "w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-all focus:border-green-500 focus:ring-2 focus:ring-green-100 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-100 dark:focus:border-green-600 dark:focus:ring-green-900/40";

export default function GenerateInstancesDialog({ templates, onClose, onGenerated }: Props) {
  const t = useTranslations("BillsPage");

  const eligible = templates.filter(
    (tmpl) => !tmpl.is_archived && !tmpl.is_paused && tmpl.frequency !== "one_off",
  );

  const [months, setMonths] = useState("6");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(
    () => new Set(eligible.map((tmpl) => tmpl.id)),
  );
  const [created, setCreated] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const monthsNum = parseInt(months, 10);
  const monthsValid = !isNaN(monthsNum) && monthsNum >= 1 && monthsNum <= 24;
  const canSubmit =
    eligible.length > 0 && selectedIds.size > 0 && monthsValid && !submitting;

  function toggleId(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleGenerate() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await generateInstances(monthsNum, Array.from(selectedIds));
      setCreated(res.created);
      onGenerated();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("generateDialog.error"));
    } finally {
      setSubmitting(false);
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="generate-dialog-title"
        onKeyDown={(e) => e.key === "Escape" && !submitting && onClose()}
        className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:bg-slate-800 dark:border-slate-700"
      >
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
          <CalendarPlus size={22} />
        </div>
        <h2
          id="generate-dialog-title"
          className="mb-1 text-lg font-semibold text-slate-800 dark:text-slate-100"
        >
          {t("generateDialog.title")}
        </h2>
        <p className="mb-5 text-sm text-slate-500 dark:text-slate-400">
          {t("generateDialog.description")}
        </p>

        {eligible.length === 0 ? (
          <p className="mb-5 rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-500 dark:bg-slate-700/50 dark:text-slate-400">
            {t("generateDialog.noEligible")}
          </p>
        ) : created === null ? (
          <>
            <div className="mb-4">
              <label
                htmlFor="generate-months"
                className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500"
              >
                {t("generateDialog.monthsLabel")}
              </label>
              <input
                id="generate-months"
                type="number"
                min={1}
                max={24}
                value={months}
                onChange={(e) => setMonths(e.target.value)}
                className={inputClass}
              />
            </div>

            <fieldset className="mb-5">
              <legend className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
                {t("generateDialog.templatesLabel")}
              </legend>
              <div className="max-h-56 space-y-1.5 overflow-y-auto rounded-xl border border-slate-200 p-3 dark:border-slate-600">
                {eligible.map((tmpl) => (
                  <label
                    key={tmpl.id}
                    className="flex cursor-pointer items-center gap-2.5 text-sm text-slate-700 dark:text-slate-300"
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.has(tmpl.id)}
                      onChange={() => toggleId(tmpl.id)}
                      className="h-4 w-4 shrink-0 rounded accent-green-700"
                    />
                    <span className="flex-1 truncate">{tmpl.name}</span>
                    <span className="shrink-0 text-xs text-slate-400 dark:text-slate-500">
                      {tmpl.amount} {tmpl.currency}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          </>
        ) : (
          <p
            role="status"
            className="mb-5 rounded-xl bg-green-50 px-3 py-2 text-sm text-green-700 dark:bg-green-900/20 dark:text-green-400"
          >
            {t("generateDialog.created", { count: created })}
          </p>
        )}

        {error && (
          <p className="mb-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </p>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            disabled={submitting}
            className="flex-1 rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            {created === null ? t("cancel") : t("generateDialog.close")}
          </button>
          {created === null && (
            <button
              onClick={handleGenerate}
              disabled={!canSubmit}
              className="flex-1 rounded-xl border border-green-700 bg-green-700 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:border-green-800 hover:bg-green-800 disabled:opacity-50"
            >
              {submitting ? t("generateDialog.submitting") : t("generateDialog.submit")}
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
