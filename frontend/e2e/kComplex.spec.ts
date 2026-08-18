import { expect, test } from '@playwright/test';

test('opens SN001 morphology-verified K-complexes and retains rejected V0 candidates', async ({
  page,
}) => {
  test.setTimeout(120_000);
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

  const insights = page.getByRole('region', { name: 'Sleep Insights' });
  await expect(insights).toContainText('22 verified', {
    timeout: 60_000,
  });
  await insights.screenshot({
    path: 'artifacts/screenshots/hmc-sn001-k-complex-ready.png',
  });

  await insights.getByRole('button', { name: /K-Complex 22 verified/ }).click();
  await expect(insights.getByTestId('k-complex-panel')).toBeVisible();
  await insights.getByText('K-Complex candidate 14').first().click();

  const eeg = page.locator('[aria-labelledby="real-eeg-title"]');
  await expect(
    page.getByRole('button', { name: /KC trough at/ }),
  ).toBeVisible();
  await expect(page.getByTestId('window-range')).toContainText(
    'cursor 2452.67 s',
  );
  await eeg.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: 'artifacts/screenshots/hmc-sn001-k-complex-n2-marker.png',
  });
  await eeg.screenshot({
    path: 'artifacts/screenshots/hmc-sn001-k-complex-focused-trough.png',
  });

  await insights.getByRole('button', { name: 'Next KC' }).click();
  await expect(page.getByTestId('window-range')).toContainText(
    'cursor 2453.77 s',
  );
  await expect(
    insights.getByRole('button', { name: 'Looks right' }),
  ).toBeVisible();
  await expect(
    insights.getByRole('button', { name: 'Mark K-Complex manually' }),
  ).toBeVisible();
  await insights.getByLabel('Show rejected V0 candidates').check();
  await expect(insights.getByText('First K-Complex').first()).toBeVisible();
});
