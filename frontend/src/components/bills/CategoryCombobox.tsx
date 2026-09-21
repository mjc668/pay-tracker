"use client";

import { useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import {
  categoryLabel,
  createCategory,
  type Category,
} from "@/lib/categories-api";
import { categoryValue, sortCategories } from "@/lib/categories";

const ADD_NEW_VALUE = "__add_new__";

interface Props {
  id: string;
  value: Category | null;
  categories: Category[];
  onChange: (category: Category | null) => void;
  /** Called after the inline "Add new…" flow creates a category. */
  onCreated: (category: Category) => void;
}

const fieldClass =
  "w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-green-500 focus:ring-2 focus:ring-green-100 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-100 dark:focus:border-green-600 dark:focus:ring-green-900/40";

export default function CategoryCombobox({
  id,
  value,
  categories,
  onChange,
  onCreated,
}: Props) {
  const t = useTranslations();
  const tc = useTranslations("CategoryCombobox");
  const tf = useTranslations("BillTemplateForm");
  const locale = useLocale();

  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Archived categories are hidden, but an edited bill may still reference
  // one — keep it as an option so the current value stays visible.
  const selectable = categories.filter((category) => !category.is_archived);
  const withCurrent =
    value !== null && !selectable.some((category) => category.id === value.id)
      ? [...selectable, value]
      : selectable;
  const options = sortCategories(withCurrent, locale, t);

  function handleSelect(raw: string) {
    if (raw === ADD_NEW_VALUE) {
      setAdding(true);
      setError(null);
      return;
    }
    onChange(options.find((category) => categoryValue(category) === raw) ?? null);
  }

  function cancelAdd() {
    setAdding(false);
    setDraft("");
    setError(null);
  }

  async function submitAdd() {
    const name = draft.trim();
    if (!name || saving) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createCategory(name);
      onCreated(created);
      onChange(created);
      setAdding(false);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("addFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <select
        id={id}
        value={value !== null ? categoryValue(value) : ""}
        onChange={(e) => handleSelect(e.target.value)}
        className={fieldClass}
      >
        <option value="">—</option>
        {options.map((category) => (
          <option key={category.id} value={categoryValue(category)}>
            {categoryLabel(category, t)}
          </option>
        ))}
        <option value={ADD_NEW_VALUE}>{tf("categoryAdd")}</option>
      </select>

      {adding && (
        <div className="mt-2 flex items-center gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void submitAdd();
              } else if (e.key === "Escape") {
                cancelAdd();
              }
            }}
            placeholder={tc("placeholder")}
            maxLength={50}
            autoFocus
            aria-label={tc("placeholder")}
            className={fieldClass}
          />
          <button
            type="button"
            onClick={() => void submitAdd()}
            disabled={saving || draft.trim() === ""}
            aria-label={tc("addConfirm")}
            className="shrink-0 rounded-xl border border-green-700 bg-green-700 p-2.5 text-white shadow-sm transition-all hover:border-green-800 hover:bg-green-800 disabled:opacity-50"
          >
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
          </button>
          <button
            type="button"
            onClick={cancelAdd}
            disabled={saving}
            aria-label={tc("addCancel")}
            className="shrink-0 rounded-xl border border-slate-200 bg-white p-2.5 text-slate-500 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700"
          >
            <X size={15} />
          </button>
        </div>
      )}

      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </div>
  );
}
