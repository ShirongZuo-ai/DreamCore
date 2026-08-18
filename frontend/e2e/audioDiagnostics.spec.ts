import { expect, test, type Page } from '@playwright/test';

type AudioDiagnostic = {
  contextCount: number;
  contextState: AudioContextState | 'unavailable';
  resumeCount: number;
  oscillatorCount: number;
  gainCount: number;
  filterCount: number;
};

async function loadRealSession(page: Page) {
  await page.goto('/datasets');
  const row = page.getByTestId('session-row-sc4001-alpha-v1');
  await expect(row).toBeVisible();
  await row.click();
  await page.getByRole('button', { name: 'Open Viewer' }).click();
  await expect(page).toHaveURL(/\/live$/);
  await expect(page.getByTestId('sonification-panel')).toBeVisible();
}

async function diagnostic(page: Page): Promise<AudioDiagnostic> {
  return page.evaluate(
    () =>
      (
        window as typeof window & {
          __dreamcoreAudioDiagnostic: AudioDiagnostic;
        }
      ).__dreamcoreAudioDiagnostic,
  );
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const NativeAudioContext = window.AudioContext;
    const state: AudioDiagnostic = {
      contextCount: 0,
      contextState: NativeAudioContext ? 'suspended' : 'unavailable',
      resumeCount: 0,
      oscillatorCount: 0,
      gainCount: 0,
      filterCount: 0,
    };
    (
      window as typeof window & {
        __dreamcoreAudioDiagnostic: AudioDiagnostic;
      }
    ).__dreamcoreAudioDiagnostic = state;
    if (!NativeAudioContext) return;
    class DiagnosticAudioContext extends NativeAudioContext {
      constructor(options?: AudioContextOptions) {
        super(options);
        state.contextCount += 1;
        state.contextState = this.state;
        this.addEventListener('statechange', () => {
          state.contextState = this.state;
        });
      }

      override async resume() {
        state.resumeCount += 1;
        await super.resume();
        state.contextState = this.state;
      }

      override createOscillator() {
        state.oscillatorCount += 1;
        return super.createOscillator();
      }

      override createGain() {
        state.gainCount += 1;
        return super.createGain();
      }

      override createBiquadFilter() {
        state.filterCount += 1;
        return super.createBiquadFilter();
      }
    }
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: DiagnosticAudioContext,
    });
  });
});

test('output test schedules an audible path without advancing replay', async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      consoleErrors.push(`${message.type()}: ${message.text()}`);
    }
  });
  await loadRealSession(page);
  await page.getByRole('button', { name: 'Audio output test' }).click();
  await expect(page.getByTestId('audio-state')).toContainText(
    'AudioContext: running',
  );
  await expect(page.getByTestId('audio-state')).toContainText('Replay: idle');
  expect(await diagnostic(page)).toMatchObject({
    contextCount: 1,
    contextState: 'running',
    resumeCount: 1,
    oscillatorCount: 1,
    gainCount: 2,
    filterCount: 1,
  });
  await expect(page.getByTestId('last-audio-trigger')).toContainText(
    'audio_output_test',
  );
  await expect(page.getByTestId('last-audio-trigger')).toContainText(
    'MIDI 69 (440.0 Hz) · velocity 0.350 → rendered 0.350 · cutoff 2400.0 Hz · Q 0.70 · peak 0.056',
  );
  expect(consoleErrors).toEqual([]);
});

test('one Start Sonification action starts authoritative replay and plays a crossed real EOG event once', async ({
  page,
}) => {
  await loadRealSession(page);
  await page.getByLabel('Session seek').fill('30696');
  await expect(page.getByTestId('sonification-panel')).toBeVisible();
  await expect(page.getByTestId('audio-state')).toContainText('Replay: paused');
  await page.getByRole('button', { name: 'Start Sonification' }).click();
  await expect(page.getByTestId('audio-state')).toContainText(
    'AudioContext: running',
  );
  await expect(page.getByTestId('audio-state')).toContainText(
    'Audio engine: enabled',
  );
  await expect(page.getByTestId('audio-state')).toContainText(
    'Replay: playing',
  );
  await expect(page.getByTestId('last-audio-trigger')).toContainText(
    'candidate_event',
    { timeout: 5000 },
  );
  await expect(page.getByTestId('last-audio-trigger')).toContainText(
    'trigger 30697.00 s',
  );
  const audio = await diagnostic(page);
  expect(audio.oscillatorCount).toBeGreaterThanOrEqual(1);
  await expect(page.getByTestId('last-audio-trigger')).toContainText(
    'MIDI 55 (196.0 Hz) · velocity 0.317 → rendered 0.317 · cutoff 630.0 Hz · Q 0.70 · peak 0.051',
  );

  await page.getByRole('button', { name: 'Pause replay' }).click();
  const countAfterPause = (await diagnostic(page)).oscillatorCount;
  await page.waitForTimeout(750);
  expect((await diagnostic(page)).oscillatorCount).toBe(countAfterPause);
});
