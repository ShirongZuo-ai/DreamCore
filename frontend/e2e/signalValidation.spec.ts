import { expect, test, type Page } from '@playwright/test';

async function openSn001(page: Page) {
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
  await expect(page).toHaveURL(/\/live$/);
  await expect(page.getByTestId('real-eeg-window')).toBeVisible({
    timeout: 30_000,
  });
}

test('SN001 sparse Alpha and Eye Movement event semantics are explicit', async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1100 });
  await openSn001(page);

  await page.getByLabel('Session seek').fill('4352');
  const eye = page.getByTestId('eye-movement-panel');
  await eye.scrollIntoViewIfNeeded();
  const event = page
    .getByTestId('eye-event-markers')
    .getByRole('button', { name: /4351\.32 s/ });
  await expect(event).toBeVisible({ timeout: 30_000 });
  await event.click();
  const selected = page.getByTestId('selected-eye-event');
  await expect(selected).toContainText('4351.32 s');
  await expect(selected).toContainText('43.16 µV');
  await expect(selected).toContainText('0.35');
  await expect(selected).toContainText('N2');
  await expect(eye).toContainText('Cursor 4352.00 s');
  await eye.screenshot({
    path: 'artifacts/screenshots/signal-validation-v1-eye-after.png',
  });

  await page.getByLabel('Session seek').fill('4370');
  const alpha = page.getByRole('region', { name: 'Alpha V1 derived metrics' });
  await alpha.scrollIntoViewIfNeeded();
  await expect(alpha).toContainText('Primary signal EEG O2-M1');
  await expect(alpha).not.toContainText('EEG F4-M1');
  await expect(page.getByTestId('product-iaf')).toContainText(
    'No clear Alpha peak',
  );
  await expect(page.getByTestId('alpha-absolute-chart')).toHaveAttribute(
    'data-point-rendering',
    'observed-glyphs',
  );
  await expect(page.getByTestId('alpha-absolute-chart')).toHaveAttribute(
    'data-point-connection',
    'discrete',
  );
  await expect(page.getByTestId('alpha-absolute-chart')).toHaveAttribute(
    'data-point-count',
    '12',
  );
  await alpha.screenshot({
    path: 'artifacts/screenshots/signal-validation-v1-alpha-after.png',
  });

  await page.getByLabel('Session seek').fill('4380');
  await alpha.getByText('Advanced Alpha diagnostics').click();
  await expect(alpha).toContainText('IAF confidence: 0.398');
  await expect(alpha).toContainText('Product display criterion: 1.000');
  await expect(page.getByTestId('product-iaf')).toContainText(
    'No clear Alpha peak',
  );
});

test('internal Signal Validation dashboard renders completed metrics', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto('/validation');
  await expect(
    page.getByRole('heading', { name: 'Signal Validation', level: 1 }),
  ).toBeVisible();
  await expect(page.getByText('Human QC pending')).toBeVisible();
  await expect(
    page.getByText(/No expert trough landmark exists/),
  ).toBeVisible();
  await expect(page.getByRole('cell', { name: 'noise only' })).toBeVisible();
  await page.screenshot({
    path: 'artifacts/screenshots/signal-validation-v1-dashboard.png',
    fullPage: true,
  });
});
