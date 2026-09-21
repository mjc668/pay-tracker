import { categoryLabel, type Category, type CategoryTranslator } from "./categories-api";

/**
 * Positional border palette. Colors are assigned by the category's index in a
 * sorted list instead of by a hardcoded key, so custom categories get one too.
 */
export const CATEGORY_BORDER_PALETTE: readonly string[] = [
  "border-l-blue-400 dark:border-l-blue-500",
  "border-l-purple-400 dark:border-l-purple-500",
  "border-l-rose-400 dark:border-l-rose-500",
  "border-l-orange-400 dark:border-l-orange-500",
  "border-l-slate-400 dark:border-l-slate-500",
  "border-l-violet-400 dark:border-l-violet-500",
  "border-l-cyan-500 dark:border-l-cyan-400",
  "border-l-emerald-400 dark:border-l-emerald-500",
  "border-l-slate-300 dark:border-l-slate-600",
];

/** Palette entry for a zero-based position; wraps for long lists. */
export function categoryColor(index: number): string {
  const length = CATEGORY_BORDER_PALETTE.length;
  const safeIndex = ((index % length) + length) % length;
  return CATEGORY_BORDER_PALETTE[safeIndex];
}

/**
 * Stable value for <option> elements and filter state. Defaults keep their
 * `key` (so it survives renames); custom categories use their id.
 */
export function categoryValue(category: Category): string {
  return category.key ?? String(category.id);
}

/** Alphabetical by rendered label, in the active locale. */
export function sortCategories(
  categories: Category[],
  locale: string,
  t: CategoryTranslator,
): Category[] {
  return [...categories].sort((a, b) =>
    categoryLabel(a, t).localeCompare(categoryLabel(b, t), locale),
  );
}
