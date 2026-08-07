import { expect, test, type Page } from '@playwright/test';

async function loadRealAlphaSession(page: Page) {
  await page.goto('/datasets');
  const row = page.getByTestId('session-row-sc4001-alpha-v1');
  const mobileCard = page.getByTestId('mobile-session-sc4001-alpha-v1');
  await expect
    .poll(async () => (await row.isVisible()) || (await mobileCard.isVisible()))
    .toBe(true);
  if (await mobileCard.isVisible()) {
    await mobileCard.getByRole('button').click();
  } else {
    await row.click();
  }
  await page.getByRole('button', { name: 'Load Session' }).click();
  await expect(page).toHaveURL(/\/live$/);
  await expect(page.getByTestId('real-eeg-window')).toBeVisible();
}

test('SC4001 real EEG and synchronized Alpha viewer load through HTTP', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await loadRealAlphaSession(page);
  await expect(page.getByText('REAL PUBLIC EEG DATA').first()).toBeVisible();
  await expect(page.getByText('EEG Fpz-Cz').first()).toBeVisible();
  await expect(page.getByText('EEG Pz-Oz').first()).toBeVisible();
  await expect(page.getByText('Imported sleep-stage annotation')).toBeVisible();
  await expect(page.getByText('SIMULATED CONTROL DEMAND')).toBeAttached();
  await expect(page.getByText('NOT ULTRASOUND DOSE')).toBeAttached();
  await page.screenshot({
    path: 'artifacts/screenshots/sc4001-real-eeg-desktop.png',
    fullPage: true,
  });
});

test('Alpha comparison and W to N1 transition remain provenance-explicit', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await loadRealAlphaSession(page);
  const stagePanel = page.getByRole('region', { name: 'Sleep stage overlay' });
  await expect(stagePanel).toContainText('W');
  await expect(stagePanel).toContainText('N1');
  await expect(page.getByText('No reliable alpha peak')).toHaveCount(2);
  const alphaPanel = page.getByRole('region', {
    name: 'Alpha V1 derived metrics',
  });
  await alphaPanel.scrollIntoViewIfNeeded();
  await alphaPanel.screenshot({
    path: 'artifacts/screenshots/sc4001-alpha-comparison.png',
  });
  await stagePanel.screenshot({
    path: 'artifacts/screenshots/sc4001-w-to-n1-transition.png',
  });
});

test('manual window change updates the shared range and bounded EEG request', async ({
  page,
}) => {
  await loadRealAlphaSession(page);
  const before = await page.getByTestId('window-range').innerText();
  await page.getByRole('button', { name: /Next/ }).click();
  await expect(page.getByTestId('window-range')).not.toHaveText(before);
  await expect(page.getByTestId('real-eeg-window')).toBeVisible();
});

test('SC4001 viewer has no page-level horizontal overflow at 390px', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loadRealAlphaSession(page);
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);
  await page.screenshot({
    path: 'artifacts/screenshots/sc4001-real-eeg-mobile-390.png',
    fullPage: true,
  });
});
