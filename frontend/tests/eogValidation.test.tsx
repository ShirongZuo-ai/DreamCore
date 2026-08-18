import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { EogValidationPanel } from '../src/components/eyeMovement/EogValidationPanel';

function response(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ eog_validation_api_version: 'v1', data }),
  } as Response);
}

const candidate = {
  review_id: 'candidate:hmc:001',
  sample_kind: 'candidate',
  candidate_id: 'candidate-1',
  dataset_id: 'hmc',
  subject_id: 'SN001',
  recording_id: 'SN001',
  source_channel: 'EOG E1-M2',
  timestamp: '100.0',
  normalized_stage: 'N2',
  agreement_class: 'matched_dual_eog',
  confidence: '0.7',
  amplitude_uv: '21.5',
};

const recording = {
  available: true,
  validation_version: 'eog-validation-v1',
  contract_sha256: 'abc123def456789',
  manual_review_status: 'pending',
  channels: [],
  agreement: [
    {
      tolerance_s: '0.5',
      channel_a: 'EOG E1-M2',
      channel_b: 'EOG E2-M2',
      channel_a_events: '20',
      channel_b_events: '22',
      matched_events: '10',
      channel_a_only: '10',
      channel_b_only: '12',
      matched_proportion: '0.4545',
    },
  ],
  stage_distribution: [],
  scorer_disagreement: [],
};

const progress = {
  candidate_reviewed: 0,
  candidate_total: 150,
  control_reviewed: 0,
  control_total: 150,
  label_counts: {},
  datasets: { hmc: { reviewed: 0, total: 100 } },
};

describe('Eye Movement Validation Viewer panel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('focuses ±5 s, shows dual EOG context, saves labels, and reloads notes', async () => {
    const onFocus = vi.fn();
    let saved = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input);
      if (url.includes('/recording?')) return response(recording);
      if (url.includes('kind=candidate')) return response([candidate]);
      if (url.includes('kind=control')) return response([]);
      if (url.endsWith('/progress'))
        return response(
          saved
            ? {
                ...progress,
                candidate_reviewed: 1,
                label_counts: { Uncertain: 1 },
              }
            : progress,
        );
      if (url.includes('/focus?'))
        return response({
          sample: candidate,
          focus_start_s: 95,
          focus_end_s: 105,
          candidate_timestamp: 100,
          eog_signals: [
            { signal_id: 'eog-1', channel: 'EOG E1-M2', sampling_rate_hz: 256 },
            { signal_id: 'eog-2', channel: 'EOG E2-M2', sampling_rate_hz: 256 },
          ],
          eeg_signals: [
            { signal_id: 'eeg-1', channel: 'EEG F4-M1', sampling_rate_hz: 256 },
          ],
          review: saved
            ? {
                review_id: candidate.review_id,
                review_label: 'Uncertain',
                notes: 'needs second reviewer',
              }
            : null,
        });
      if (url.includes('/filtered-window?'))
        return response({
          session_id: 'SN001',
          channel: 'EOG E1-M2',
          start_s: 95,
          end_s: 105,
          sampling_rate_hz: 1,
          unit: 'uV',
          timestamps: [95, 96, 97, 98, 99, 100, 101, 102, 103, 104],
          samples: [0, 1, 0, -1, 0, 2, 0, -1, 0, 1],
          provenance: 'derived',
        });
      if (url.endsWith('/reviews') && init?.method === 'POST') {
        saved = true;
        return response({ review_id: candidate.review_id });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<EogValidationPanel sessionId="SN001" onFocus={onFocus} />);
    const summary = await screen.findByText('Eye Movement Validation');
    await userEvent.click(summary);
    expect(summary).toBeVisible();
    await userEvent.click(
      screen.getByRole('button', { name: 'Open focused ±5 s review' }),
    );
    await waitFor(() => expect(onFocus).toHaveBeenCalledWith(95, 105, 100));
    expect(await screen.findByText(/EOG E1-M2, EOG E2-M2/)).toBeVisible();
    expect(screen.getByTestId('validation-filtered-eog')).toBeVisible();

    await userEvent.click(screen.getByRole('button', { name: 'Uncertain' }));
    await userEvent.type(
      screen.getByLabelText('Researcher notes'),
      'needs second reviewer',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Save review' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Review saved locally',
    );

    await userEvent.click(
      screen.getByRole('button', { name: 'Open focused ±5 s review' }),
    );
    expect(await screen.findByLabelText('Researcher notes')).toHaveValue(
      'needs second reviewer',
    );
    expect(screen.getByRole('button', { name: 'Uncertain' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});
