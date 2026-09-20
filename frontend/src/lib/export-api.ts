import { apiFetch, getApiBaseUrl, extractApiError } from "./api";

export async function downloadBackup(): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}/export/json`, {
    credentials: "include",
  });

  if (!res.ok) throw await extractApiError(res);

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const today = new Date().toISOString().slice(0, 10);
  a.download = `pay-tracker-backup-${today}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function restoreFromBackup(
  file: File
): Promise<{ restored_templates: number; restored_instances: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${getApiBaseUrl()}/export/restore`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!res.ok) throw await extractApiError(res);
  return res.json();
}

export async function getExportSummary(): Promise<{
  bill_count: number;
  payment_count: number;
}> {
  return apiFetch("/export/summary");
}

export async function getLastSnapshot(): Promise<{ created_at: string } | null> {
  const res = await fetch(`${getApiBaseUrl()}/export/last-snapshot`, {
    credentials: "include",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw await extractApiError(res);
  return res.json();
}

export async function restoreFromSnapshot(): Promise<{
  restored_templates: number;
  restored_instances: number;
}> {
  return apiFetch("/export/restore-snapshot", { method: "POST" });
}

export async function downloadXlsx(year: number): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}/export/xlsx?year=${year}`, {
    credentials: "include",
  });

  if (!res.ok) throw await extractApiError(res);

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `pay-tracker-${year}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}
