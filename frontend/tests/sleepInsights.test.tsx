import { render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import { SleepInsightsPanel } from '../src/components/insights/SleepInsightsPanel';
import { useAutomaticAnalysis } from '../src/hooks/useAutomaticAnalysis';
import type {
  AutomaticAnalysisApi,
  ProductAnalysisStatus,
} from '../src/services/automaticAnalysisApi';

function status(state: 'ANALYZING' | 'READY'): ProductAnalysisStatus {
  return {
    analysis_api_version: 'dreamcore.automatic_analysis.v1',
    session_id: 'SN001',
    poll_interval_ms: 1,
    features: {
      eye_movement: {
        feature: 'eye_movement',
        state,
        summary:
          state === 'READY'
            ? 'Ready · 403 EOG E1-M2 detections / 366 EOG E2-M2 detections'
            : 'Analyzing...',
      },
      alpha: {
        feature: 'alpha',
        state,
        summary: state === 'READY' ? 'Ready' : 'Analyzing...',
      },
      wake_music_profile: {
        feature: 'wake_music_profile',
        state,
        summary: state === 'READY' ? 'Ready to generate' : 'Analyzing...',
      },
      k_complex: {
        feature: 'k_complex',
        state,
        summary: state === 'READY' ? '42 verified' : 'Analyzing...',
      },
    },
  };
}

function Harness({ api }: { api: AutomaticAnalysisApi }) {
  const current = useAutomaticAnalysis({
    sessionId: 'SN001',
    enabled: true,
    api,
  });
  return <SleepInsightsPanel status={current} />;
}

it('moves product insights from Analyzing to Ready without artifact language', async () => {
  const ensure = vi
    .fn<AutomaticAnalysisApi['ensure']>()
    .mockResolvedValueOnce(status('ANALYZING'))
    .mockResolvedValue(status('READY'));
  render(<Harness api={{ ensure }} />);

  expect(screen.getAllByText('Analyzing...').length).toBeGreaterThan(0);
  expect(
    await screen.findByText(
      'Ready · 403 EOG E1-M2 detections / 366 EOG E2-M2 detections',
    ),
  ).toBeVisible();
  await waitFor(() => expect(ensure).toHaveBeenCalledTimes(2));
  expect(screen.getByText('Ready to generate')).toBeVisible();
  expect(screen.queryByText(/derived artifact/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/not computed/i)).not.toBeInTheDocument();
  expect(screen.getByText('42 verified')).toBeVisible();
});
