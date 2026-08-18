import { expect, test } from '@playwright/test';

test('real HMC candidate opens a bounded dual-EOG validation focus', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/datasets');
  await page
    .getByRole('combobox', { name: 'Dataset', exact: true })
    .selectOption({ label: 'HMC Sleep Staging' });
  await page
    .getByRole('combobox', { name: 'Subject' })
    .selectOption({ label: 'SN001' });
  await page
    .getByRole('combobox', { name: 'Recording' })
    .selectOption({ label: 'SN001' });
  await page.getByRole('button', { name: 'Open Viewer' }).click();

  const summary = page.getByText('Eye Movement Validation');
  await expect(summary).toBeVisible();
  await summary.click();
  await expect(page.getByText(/6078\.316 s/)).toBeVisible();
  await page.getByRole('button', { name: 'Open focused ±5 s review' }).click();
  await expect(page.getByText(/EOG E1-M2, EOG E2-M2/)).toBeVisible();
  await expect(page.getByTestId('validation-filtered-eog')).toBeVisible();
  await expect(page.getByTestId('window-range')).toContainText(
    /window .*–.* s/,
  );
  await expect(page.getByTestId('raw-eog-track')).toHaveCount(2);
  await expect(page.getByTestId('real-eeg-window')).toBeVisible();
  await expect(page.getByTestId('current-imported-stage')).toContainText(
    /Current imported stage:/,
  );
  await page.getByRole('button', { name: 'Next review sample' }).click();
  await page.getByRole('button', { name: 'Previous review sample' }).click();
  await page.getByRole('button', { name: 'Open focused ±5 s review' }).click();
  await expect(page.getByText(/6078\.316 s/)).toBeVisible();
  await expect(page.getByTestId('validation-filtered-eog')).toBeVisible();
  await page.screenshot({
    path: 'artifacts/screenshots/eog-validation-hmc-sn001.png',
    fullPage: true,
  });
});
