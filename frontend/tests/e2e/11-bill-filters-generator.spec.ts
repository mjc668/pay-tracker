/**
 * Flow 11: Bills filters and the series generator
 * Risk: filters fail to narrow the grouped bill list / clearing does not
 *       restore it, or generating payments does not create future-month
 *       instances for recurring bills.
 * Real boundaries: auth, POST /bills, GET /bills, POST /bills/generate-instances,
 *                  GET /bills/payments, client-side render and filtering.
 */
import { test, expect } from '@playwright/test';
import { loginNewUser, createBillViaApi } from './helpers';

test('bill filters narrow the grouped list and clearing restores it', async ({ page }) => {
  const stamp = Date.now();
  const activeName = `E2E Active ${stamp}`;
  const pausedName = `E2E Paused ${stamp}`;

  // Setup: one active and one paused bill in different categories
  await loginNewUser(page);
  await createBillViaApi(page, activeName);
  await createBillViaApi(page, pausedName, { category: 'housing', is_paused: true });

  await page.goto('/dashboard/bills');
  await expect(page.getByText(activeName)).toBeVisible();
  await expect(page.getByText(pausedName)).toBeVisible();

  const filters = page.getByTestId('bill-filters');

  // Step: name search narrows to the paused bill
  await filters.getByLabel('Search').fill('Paused');
  await expect(page.getByText(pausedName)).toBeVisible();
  await expect(page.getByText(activeName)).not.toBeVisible();

  // Step: the state filter narrows to paused bills
  await filters.getByLabel('Search').fill('');
  await filters.getByLabel('Status').selectOption('paused');
  await expect(page.getByText(pausedName)).toBeVisible();
  await expect(page.getByText(activeName)).not.toBeVisible();

  // Step: clearing filters restores both
  await filters.getByRole('button', { name: 'Clear filters' }).click();
  await expect(page.getByText(activeName)).toBeVisible();
  await expect(page.getByText(pausedName)).toBeVisible();

  // Assert: a search with no hits shows the distinct "no matches" state
  await filters.getByLabel('Search').fill('zzz-no-such-bill');
  await expect(page.getByText('No bills match these filters')).toBeVisible();
  await page
    .getByTestId('bill-no-matches')
    .getByRole('button', { name: 'Clear filters' })
    .click();
  await expect(page.getByText(activeName)).toBeVisible();
  await expect(page.getByText(pausedName)).toBeVisible();
});

test('generating payments creates future instances for a recurring bill', async ({ page }) => {
  const billName = `E2E Generate ${Date.now()}`;

  // Setup: one active monthly bill
  await loginNewUser(page);
  await createBillViaApi(page, billName);

  await page.goto('/dashboard/bills');
  await expect(page.getByText(billName)).toBeVisible();

  // Step: open the generator and request two months
  await page.getByRole('button', { name: 'Generate payments' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(billName)).toBeVisible();

  await dialog.getByLabel('Months ahead').fill('2');
  await dialog.getByRole('button', { name: 'Generate' }).click();

  // Assert: the dialog reports the creation
  await expect(dialog.getByText(/Created \d+ payments?/)).toBeVisible();

  await dialog.getByRole('button', { name: 'Close' }).click();
  await expect(dialog).not.toBeVisible();

  // Assert: the next UTC month's instance appears on the payments page
  // (the backend generates from current UTC month + 1)
  const now = new Date();
  const nextMonthDate = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1));
  const nextMonth = `${nextMonthDate.getUTCFullYear()}-${String(
    nextMonthDate.getUTCMonth() + 1,
  ).padStart(2, '0')}`;

  await page.goto(`/dashboard/payments?month=${nextMonth}`);
  await expect(page.getByText(billName)).toBeVisible();
});
