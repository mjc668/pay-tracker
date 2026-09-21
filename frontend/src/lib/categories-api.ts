import type { useTranslations } from "next-intl";
import { apiFetch } from "./api";

/** Shape returned by every /categories endpoint (frozen API contract). */
export interface Category {
  id: number;
  /** Stable key for the nine seeded defaults; null for user-created ones. */
  key: string | null;
  /** User-facing name; null for defaults that were never renamed. */
  name: string | null;
  is_archived: boolean;
}

/** Translator accepted by {@link categoryLabel} — use a root-level useTranslations(). */
export type CategoryTranslator = ReturnType<typeof useTranslations>;

export function fetchCategories(includeArchived = false): Promise<Category[]> {
  const qs = includeArchived ? "?include_archived=true" : "";
  return apiFetch<Category[]>(`/categories${qs}`);
}

export function createCategory(name: string): Promise<Category> {
  return apiFetch<Category>("/categories", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateCategory(
  id: number,
  data: { name?: string; is_archived?: boolean },
): Promise<Category> {
  return apiFetch<Category>(`/categories/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

/** Resolves with 204 when unused; rejects with the server's 400 message when in use. */
export function deleteCategory(id: number): Promise<void> {
  return apiFetch<void>(`/categories/${id}`, { method: "DELETE" });
}

/**
 * Rendered label rule from the frozen contract:
 * `category.name ?? t("Categories." + category.key)`, `""` when both are null.
 */
export function categoryLabel(category: Category, t: CategoryTranslator): string {
  if (category.name !== null) return category.name;
  if (category.key === null) return "";
  return t(`Categories.${category.key}` as never);
}
