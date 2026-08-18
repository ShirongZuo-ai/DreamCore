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
  await page.getByRole('button', { name: 'Open Viewer' }).click();
  await expect(page).toHaveURL(/\/live$/);
  await expect(page.getByTestId('real-eeg-window')).toBeVisible({
    timeout: 15_000,
  });
}

test('SC4001 real EOG is the primary synchronized research and sonification path', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await loadRealAlphaSession(page);
  await expect(page.getByTestId('raw-eog-track')).toBeVisible();
  await expect(page.getByTestId('filtered-eog-track')).toBeVisible();
  const eyePanel = page.getByTestId('eye-movement-panel');
  await expect(eyePanel).toHaveAttribute('data-coverage-state', 'available');
  await expect(page.getByTestId('eye-feature-coverage')).toContainText(
    '4.0–79500.0 s',
  );
  await expect(page.getByTestId('sonification-panel')).toHaveAttribute(
    'data-source',
    'eye_movement',
  );
  await expect(
    page.getByRole('radio', { name: 'Eye Movement', exact: true }),
  ).toBeChecked();
  const ordering = await page.evaluate(() => {
    const eye = document.querySelector('[data-testid="eye-movement-panel"]');
    const alpha = document.querySelector(
      '[aria-label="Alpha V1 derived metrics"]',
    );
    return Boolean(
      eye &&
      alpha &&
      eye.compareDocumentPosition(alpha) & Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
  expect(ordering).toBe(true);
  await page.screenshot({
    path: 'artifacts/screenshots/sc4001-eye-movement-primary.png',
    fullPage: true,
  });
});

test('eye candidates, stage transitions and controls use one replay cursor', async ({
  page,
}) => {
  await loadRealAlphaSession(page);
  const count = page.getByTestId('reached-eye-feature-count');

  await page.getByLabel('Session seek').fill('30697');
  await expect(page.getByTestId('current-imported-stage')).toContainText('N1');
  await expect(count).not.toContainText('Reached feature rows: 0');
  await expect(page.getByTestId('eye-event-markers')).toContainText(
    'Eye Movement Candidate',
  );
  const n1DisplayEnd = Number(
    await page
      .getByTestId('eye-activity-chart')
      .getAttribute('data-display-end-timestamp'),
  );
  expect(n1DisplayEnd).toBeCloseTo(30697, 2);

  await page.getByLabel('Session seek').fill('30760');
  await expect(page.getByTestId('current-imported-stage')).toContainText('N2');
  const n2DisplayEnd = Number(
    await page
      .getByTestId('eye-activity-chart')
      .getAttribute('data-display-end-timestamp'),
  );
  expect(n2DisplayEnd).toBeCloseTo(30760, 2);
  expect(n2DisplayEnd).toBeGreaterThan(n1DisplayEnd);
  await expect(page.getByTestId('sonification-tempo-chart')).toHaveAttribute(
    'data-display-end-timestamp',
    '30760',
  );
});

test('browser audio starts on demand and comparison mode remains explicit', async ({
  page,
}) => {
  await loadRealAlphaSession(page);
  await page.getByRole('button', { name: 'Start Sonification' }).click();
  await expect(page.getByTestId('audio-state')).toContainText(
    'Audio engine: enabled',
  );
  await expect(page.getByTestId('audio-state')).toContainText(
    'Replay: playing',
  );
  await page.getByRole('button', { name: 'Pause replay' }).click();
  await page.getByRole('radio', { name: 'Alpha', exact: true }).check();
  await expect(page.getByTestId('sonification-panel')).toHaveAttribute(
    'data-source',
    'alpha',
  );
  await page.getByLabel('None / baseline').check();
  await expect(page.getByText(/intentionally constant/)).toBeVisible();
  await page.getByRole('button', { name: 'Mute' }).click();
  await expect(page.getByTestId('audio-state')).toContainText(
    'Audio engine: muted',
  );
  await page.getByRole('button', { name: 'Reset Sound' }).click();
  await expect(page.getByTestId('audio-state')).toContainText(
    'Audio engine: disabled',
  );
});

test('outside eye-movement coverage is explicit and never rendered as zero', async ({
  page,
}) => {
  await loadRealAlphaSession(page);
  await page.getByLabel('Session seek').fill('2');
  await expect(page.getByTestId('eye-movement-panel')).toHaveAttribute(
    'data-coverage-state',
    'outside_coverage',
  );
  await expect(
    page.getByText('No precomputed eye-movement feature at this time.'),
  ).toBeVisible();
  await expect(
    page.getByText(/Missing data is not shown as zero/),
  ).toBeVisible();
});

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
    path: 'artifacts/screenshots/sc4001-replay-paused.png',
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
  await expect(page.getByTestId('product-iaf')).toContainText(
    'No clear Alpha peak',
  );
  const alphaPanel = page.getByRole('region', {
    name: 'Alpha V1 derived metrics',
  });
  await alphaPanel.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: 'artifacts/screenshots/sc4001-replay-alpha-demand.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Jump to W→N1' }).click();
  await expect(page.getByTestId('current-imported-stage')).toContainText('N1');
  await stagePanel.screenshot({
    path: 'artifacts/screenshots/sc4001-replay-w-n1-transition.png',
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

test('SC4001 explains pre-coverage replay and reaches window-end Alpha rows in seconds', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await loadRealAlphaSession(page);
  const count = page.getByTestId('visible-feature-count');

  await page.getByLabel('Session seek').fill('157.5');
  await expect(page.getByTestId('current-imported-stage')).toContainText('W');
  await expect(page.getByTestId('real-eeg-window')).toBeVisible();
  await expect(count).toContainText('Observed feature points: 0');
  await expect(count).toHaveAttribute('data-total-session-feature-rows', '270');
  await expect(
    page.getByText(
      /Cursor 157\.50 s precedes the first analysis-window end at 29760\.00 s/,
    ),
  ).toBeVisible();
  await page.screenshot({
    path: 'artifacts/screenshots/sc4001-alpha-before-coverage.png',
    fullPage: true,
  });

  await page.getByLabel('Session seek').fill('29760');
  await expect(count).toContainText('Observed feature points: 2');
  await expect(count).toHaveAttribute('data-current-feature-time', '29760');
  await expect(page.getByTestId('alpha-absolute-chart')).toBeVisible();

  await page.getByLabel('Session seek').fill('30660');
  await expect(page.getByTestId('current-imported-stage')).toContainText('N1');
  await expect(count).toHaveAttribute('data-current-feature-time', '30660');
  await page.screenshot({
    path: 'artifacts/screenshots/sc4001-alpha-n1-feature.png',
    fullPage: true,
  });

  await page.getByLabel('Session seek').fill('157.5');
  await expect(count).toContainText('Observed feature points: 0');
});

test('offline replay shows a provenance-explicit simulated intervention prompt', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await loadRealAlphaSession(page);
  const range = page.getByTestId('window-range');
  const alphaChart = page.getByTestId('alpha-absolute-chart');
  const alphaDisplayEndBefore = Number(
    await alphaChart.getAttribute('data-display-end-timestamp'),
  );
  await page.getByLabel('Replay speed').selectOption('10');
  const eventMarkers = page.getByLabel('Simulated event markers');
  const latestEventTime = async () =>
    Math.max(
      ...(
        await eventMarkers
          .locator('[data-provenance="simulated"]')
          .allTextContents()
      ).map((text) => Number(text.match(/([0-9.]+) s/)?.[1] ?? 0)),
    );
  const latestEventTimeBefore = await latestEventTime();
  await page.getByRole('button', { name: 'Start replay' }).click();
  await expect(range).toContainText('playing 10×');
  await expect
    .poll(async () => {
      const match = (await range.innerText()).match(/cursor ([0-9.]+) s/);
      return match ? Number(match[1]) : 0;
    })
    .toBeGreaterThan(30710);
  const readAlignment = () =>
    page.evaluate(() => {
      const rangeText =
        document.querySelector('[data-testid="window-range"]')?.textContent ??
        '';
      const cursorTime = Number(rangeText.match(/cursor ([0-9.]+) s/)?.[1]);
      const eeg = document.querySelector<HTMLElement>(
        '[data-testid="real-eeg-uplot"]',
      );
      const alpha = document.querySelector<HTMLElement>(
        '[data-testid="alpha-absolute-chart"]',
      );
      const demand = document.querySelector<HTMLElement>(
        '[data-testid="simulated-demand-chart"]',
      );
      const cursor = document.querySelector<HTMLElement>(
        '[data-testid="real-eeg-uplot-replay-cursor"]',
      );
      const over = eeg?.querySelector<HTMLElement>('.u-over');
      const windowMatch = rangeText.match(/window ([0-9.]+)–([0-9.]+) s/);
      const windowStart = Number(windowMatch?.[1]);
      const windowEnd = Number(windowMatch?.[2]);
      const expectedCursorLeft =
        (over?.getBoundingClientRect().left ?? 0) +
        (over?.getBoundingClientRect().width ?? 0) *
          ((cursorTime - windowStart) / (windowEnd - windowStart));
      return {
        cursorTime,
        eegLastTime: Number(eeg?.dataset.lastVisibleTimestamp),
        alphaDisplayEnd: Number(alpha?.dataset.displayEndTimestamp),
        demandDisplayEnd: Number(demand?.dataset.displayEndTimestamp),
        cursorPositionSource: cursor?.dataset.positionSource,
        cursorPixelError: Math.abs(
          (cursor?.getBoundingClientRect().left ?? 0) - expectedCursorLeft,
        ),
      };
    });
  await expect
    .poll(async () => (await readAlignment()).cursorPixelError)
    .toBeLessThanOrEqual(1);
  await expect
    .poll(async () => Number.isFinite((await readAlignment()).eegLastTime))
    .toBe(true);
  const alignment = await readAlignment();
  expect(alignment.cursorTime - alignment.eegLastTime).toBeGreaterThanOrEqual(
    0,
  );
  expect(alignment.cursorTime - alignment.eegLastTime).toBeLessThanOrEqual(
    0.011,
  );
  expect(alignment.alphaDisplayEnd).toBeLessThanOrEqual(alignment.cursorTime);
  expect(alignment.cursorTime - alignment.alphaDisplayEnd).toBeLessThanOrEqual(
    30.01,
  );
  expect(alignment.demandDisplayEnd).toBeCloseTo(alignment.cursorTime, 2);
  expect(alignment.alphaDisplayEnd).toBeGreaterThan(alphaDisplayEndBefore);
  expect(alignment.cursorPositionSource).toBe('uplot-valToPos-plus-bbox');
  expect(alignment.cursorPixelError).toBeLessThanOrEqual(1);
  await expect.poll(latestEventTime).toBeGreaterThan(latestEventTimeBefore);
  await page.screenshot({
    path: 'artifacts/screenshots/sc4001-replay-playing.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Pause replay' }).click();
  const paused = await range.innerText();
  await page.waitForTimeout(500);
  await expect(range).toHaveText(paused);
  await page
    .getByRole('button', { name: 'Mark simulated intervention' })
    .click();
  const notice = page.getByRole('alert');
  await expect(notice).toContainText('SIMULATED INTERVENTION MARKED');
  await expect(notice).toContainText(
    'SIMULATED INTERVENTION — NO ULTRASOUND DELIVERED',
  );
  await expect(notice).toContainText('Observed EEG');
  await expect(page.getByText(/ultrasound applied/i)).toHaveCount(0);
  await page.getByLabel('Session seek').fill('30640');
  await expect(range).toContainText('cursor 30640.00 s');
  await expect(page.getByTestId('current-imported-stage')).toContainText('N1');
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
    path: 'artifacts/screenshots/sc4001-replay-mobile-390.png',
    fullPage: true,
  });
});
