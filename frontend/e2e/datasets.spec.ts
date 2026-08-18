import { expect, test } from '@playwright/test';

test('Dataset Library renders the canonical fixture catalog at desktop size', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/datasets');
  await expect(
    page.getByRole('heading', { name: 'Dataset Library' }),
  ).toBeVisible();
  await expect(page.getByTestId('session-row-fixture-a')).toBeVisible();
  await expect(page.getByTestId('session-row-fixture-c')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: 'artifacts/screenshots/datasets-1440x900.png',
    fullPage: false,
  });
});

test('session selection remains a review step before loading', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/datasets');
  await page.getByTestId('session-row-fixture-a').click();

  const selected = page.getByRole('region', { name: 'Selected session' });
  await expect(selected).toContainText('fixture-a');
  await expect(selected).toContainText('No replay has started');
  await page.screenshot({
    path: 'artifacts/screenshots/datasets-session-selected-1440x900.png',
    fullPage: false,
  });
});

test('selected session loads into Live Console without starting replay', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/datasets');
  await page.getByTestId('session-row-fixture-b').click();
  await page.getByRole('button', { name: 'Open Viewer' }).click();

  await expect(page).toHaveURL(/\/live$/);
  await expect(
    page.getByText('fixture-b', { exact: true }).last(),
  ).toBeVisible();
  await expect(
    page.getByText('Offline session — no hardware telemetry'),
  ).toBeVisible();
  await expect(page.getByText('62 bpm')).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: 'artifacts/screenshots/live-loaded-session-1440x900.png',
    fullPage: false,
  });
});

test('Random Session selects but does not load', async ({ page }) => {
  await page.goto('/datasets');
  await page
    .getByRole('button', { name: 'Random Session', exact: true })
    .click();
  await expect(page.getByRole('status')).toContainText('Random selection:');
  await expect(page).toHaveURL(/\/datasets$/);
});

test('missing phase capability is rendered as unavailable', async ({
  page,
}) => {
  await page.goto('/datasets');
  await page.getByTestId('session-row-fixture-b').click();
  await page.getByRole('button', { name: 'Open Viewer' }).click();

  const decisionPanel = page.getByRole('complementary', {
    name: 'AI decision panel',
  });
  await expect(decisionPanel).toContainText('Phase Estimation');
  await expect(decisionPanel).toContainText('Unavailable');
});

test('Dataset Library has no page-level overflow at 390px', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/datasets');
  await expect(
    page.getByRole('heading', { name: 'Dataset Library' }),
  ).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: 'artifacts/screenshots/datasets-390x844.png',
    fullPage: false,
  });
});

for (const representative of [
  {
    dataset: 'Sleep-EDF Expanded',
    subject: 'SC400',
    recording: 'SC4002',
    channel: 'EOG horizontal',
  },
  {
    dataset: 'HMC Sleep Staging',
    subject: 'SN001',
    recording: 'SN001',
    channel: 'EOG E1-M2',
  },
  {
    dataset: 'ISRUC-Sleep Cohort III',
    subject: 'ISRUC-C3-01',
    recording: 'isruc-c3-01',
    channel: 'LOC-A2',
  },
]) {
  test(`opens a real ${representative.dataset} recording in the unified Viewer`, async ({
    page,
  }) => {
    await page.goto('/datasets');
    await page
      .getByRole('combobox', { name: 'Dataset', exact: true })
      .selectOption({
        label: representative.dataset,
      });
    await page.getByRole('combobox', { name: 'Subject' }).selectOption({
      label: representative.subject,
    });
    await page.getByRole('combobox', { name: 'Recording' }).selectOption({
      label: representative.recording,
    });
    await expect(
      page.getByText(representative.channel, { exact: false }).first(),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Open Viewer' }).click();
    await expect(page).toHaveURL(/\/live$/);
    await expect(
      page.getByText(representative.recording, { exact: true }).last(),
    ).toBeVisible();
    await expect(
      page.getByText(representative.channel, { exact: false }).first(),
    ).toBeVisible();
    const insights = page.getByRole('region', { name: 'Sleep Insights' });
    await expect(insights).toBeVisible();
    await expect(insights).toContainText('Ready');
    await expect(insights).not.toContainText(/not computed/i);
    if (representative.recording === 'SN001') {
      await insights.screenshot({
        path: 'artifacts/screenshots/hmc-sn001-sleep-insights.png',
      });
    }
  });
}
