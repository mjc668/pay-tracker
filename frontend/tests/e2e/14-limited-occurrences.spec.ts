/**
 * Flow 14: Limited occurrences (max_occurrences)
 * Risk: the configured payment cap is ignored during series generation or
 *       current-period seeding, so a bill keeps producing instances past its
 *       last occurrence.
 * Real boundaries: auth (cookie), Bills API (POST /bills,
 *                  POST /bills/generate-instances, POST /bills/sync-instances),
 *                  Payments API (GET /bills/payments), client-side render.
 */
import { test, expect } from '@playwright/test';
import { loginNewUser } from './helpers';

/** UTC month key ("YYYY-MM") offset by `offset` months from the current one. */
function monthKeyFromUtcOffset(offset: number): string {
  const now = new Date();
  const shifted = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + offset, 1));
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, '0')}`;
}

test('monthly bill capped at 4 payments stops after month +3', async ({ page }) => {
  const billName = `E2E Capped ${Date.now()}`;

  // Setup: authenticate via API
  await loginNewUser(page);

  // Step: create a monthly bill limited to 4 payments through the UI
  await page.goto('/dashboard/bills');
  await expect(page.getByRole('button', { name: 'New Bill' })).toBeVisible();
  await page.getByRole('button', { name: 'New Bill' }).click();

  await page.getByLabel('Name').fill(billName);
  await page.getByLabel('Amount').fill('45.00');
  await page.getByLabel('Category').selectOption('utilities');
  await page.getByRole('button', { name: 'Monthly', exact: true }).click();
  await page.getByLabel('Set number of payments').check();
  await page.getByLabel('Number of payments', { exact: true }).fill('4');
  await page.getByRole('button', { name: 'Save' }).click();

  // Assert: the bill list renders the cap next to the frequency
  await expect(page.getByText(billName)).toBeVisible();
  await expect(page.getByText('4 payments')).toBeVisible();

  // Step: generate 6 months ahead in the series generator
  await page.getByRole('button', { name: 'Generate payments' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(billName)).toBeVisible();
  await dialog.getByLabel('Months ahead').fill('6');
  await dialog.getByRole('button', { name: 'Generate' }).click();
  await expect(dialog.getByText(/Created \d+ payments?/)).toBeVisible();
  await dialog.getByRole('button', { name: 'Close' }).click();

  const currentMonth = monthKeyFromUtcOffset(0);
  const monthPlus3 = monthKeyFromUtcOffset(3);
  const monthPlus4 = monthKeyFromUtcOffset(4);

  // Assert: the first occurrence (current month) exists
  await page.goto(`/dashboard/payments?month=${currentMonth}`);
  await expect(page.getByText(billName).first()).toBeVisible();

  // Assert: the fourth occurrence (month +3) exists ...
  await page.goto(`/dashboard/payments?month=${monthPlus3}`);
  await expect(page.getByText(billName).first()).toBeVisible();

  // Assert: ... but the fifth (month +4) was never generated
  await page.goto(`/dashboard/payments?month=${monthPlus4}`);
  await expect(page.getByText('No bills for this month')).toBeVisible();
  await expect(page.getByText(billName)).toHaveCount(0);
});
