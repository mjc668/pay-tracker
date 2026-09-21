/**
 * Flow 12: Interval-based recurrences (weekly + every-N-years)
 * Risk: the weekly unit does not backfill this month's occurrences, or an
 *       interval count is dropped from the payload/label — the user sees a
 *       single row for a weekly bill or a yearly bill without its "5" count.
 * Real boundaries: auth, POST /bills, GET /bills/payments, client-side form
 *                  and ICU plural rendering.
 */
import { test, expect } from '@playwright/test';
import { loginNewUser, createBillViaApi } from './helpers';

/** First day of the current local month, as the native date input expects. */
function firstDayOfMonthIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
}

test('weekly bill backfills this month and shows the weekly label', async ({ page }) => {
  const billName = `E2E Weekly ${Date.now()}`;

  // Setup: authenticate, then create a weekly bill through the form so the
  // unit pills, the first-payment-date input and the payload are all exercised.
  await loginNewUser(page);
  await page.goto('/dashboard/bills');
  await page.getByRole('button', { name: 'New Bill' }).click();
  await page.getByLabel('Name').fill(billName);
  await page.getByLabel('Amount').fill('12.00');
  await page.getByLabel('Category').selectOption('utilities');

  await page.getByRole('button', { name: 'Weekly', exact: true }).click();
  await page.getByLabel('First payment date').fill(firstDayOfMonthIso());
  await page.getByRole('button', { name: 'Save' }).click();

  // Assert: the bill itself is created
  await expect(page.getByText(billName)).toBeVisible();

  // Assert: the current month's payments list contains one row per weekly
  // occurrence (at least 4 in every calendar month for an interval of 1).
  await page.goto('/dashboard/payments');
  const rows = page.getByText(billName, { exact: true });
  await expect(rows.first()).toBeVisible();
  await expect.poll(() => rows.count()).toBeGreaterThanOrEqual(4);

  // Assert: the frequency label renders the weekly count (singular at 1)
  await page.getByLabel('Delete payment').first().click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText('Every week')).toBeVisible();
});

test('every-5-years bill renders the yearly interval count', async ({ page }) => {
  const billName = `E2E Quinquennial ${Date.now()}`;

  // Setup: annual bill with an interval count of 5
  await loginNewUser(page);
  await createBillViaApi(page, billName, { frequency: 'annual', interval_count: 5 });

  // Assert: the bills list row badge shows the yearly count
  await page.goto('/dashboard/bills');
  await expect(page.getByText(billName)).toBeVisible();
  await expect(page.getByText('Every 5 years')).toBeVisible();
});
