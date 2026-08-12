import { expect, test } from '@playwright/test';

const desktopRoutes = [
  { path: '/live', name: 'live-1440x900.png', heading: 'Live Console' },
  { path: '/review', name: 'review-1440x900.png', heading: 'Session Review' },
  {
    path: '/subject',
    name: 'subject-1440x900.png',
    heading: 'Everything is ready for your session',
  },
] as const;

for (const route of desktopRoutes) {
  test(`${route.path} renders at desktop size`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(route.path);
    await expect(
      page.getByRole('heading', { name: route.heading }),
    ).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: `artifacts/screenshots/${route.name}`,
      fullPage: false,
    });
  });
}

test('Live Console remains usable without horizontal overflow on mobile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/live');

  await expect(
    page.getByRole('button', { name: /Emergency Stop/i }),
  ).toBeVisible();
  await expect(page.getByText('Fp1', { exact: true })).toBeAttached();

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));

  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
  expect(dimensions.body).toBeLessThanOrEqual(dimensions.viewport);

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: 'artifacts/screenshots/live-390x844.png',
    fullPage: false,
  });
});

test('Emergency Stop is a local-only demo interaction', async ({ page }) => {
  await page.goto('/live');
  await page.getByRole('button', { name: /Emergency Stop/i }).click();
  await expect(page.getByRole('status')).toContainText(
    'Only this interface state changed',
  );
  await expect(
    page.getByRole('button', { name: /Reset local demo/i }),
  ).toBeVisible();
});

test('Subject View remains blind to experimental condition', async ({
  page,
}) => {
  await page.goto('/subject');
  const text = await page.getByTestId('subject-page').innerText();
  expect(text).not.toMatch(/\bActive\b/i);
  expect(text).not.toMatch(/\bSham\b/i);
});
