import { describe, expect, it } from 'vitest';

import {
  alphaAnalysisCoverage,
  emptyAlphaWindowMessage,
  productIafIsReliable,
  reachedAlphaFeatureRows,
} from '../src/lib/alphaReplayDiagnostics';
import type { AlphaFeatureRecord, ContentDescriptor } from '../src/types';

function descriptor(): ContentDescriptor {
  return {
    available: true,
    source: 'derived',
    metadata: {
      analysis: {
        time_reference: 'recording_relative',
        timestamp_field: 'window_end_s',
        timestamp_unit: 'seconds',
        evaluation_start_s: 100,
        evaluation_end_s: 200,
        analysis_window_s: 30,
        step_s: 10,
        attempted_windows: 8,
        accepted_windows: 7,
        rejected_windows: 1,
        rejection_reasons: { 'stage_transition:W+N1': 1 },
        feature_row_count: 14,
        first_feature_time_s: 130,
        last_feature_time_s: 200,
        channels: ['EEG Fpz-Cz', 'EEG Pz-Oz'],
        product_display_min_iaf_confidence: 0.5,
        product_display_context_s: 300,
      },
    },
  };
}

function feature(channel: string, endSeconds: number): AlphaFeatureRecord {
  return {
    channel,
    window_start_s: endSeconds - 30,
    window_end_s: endSeconds,
    stage: endSeconds < 160 ? 'W' : 'N1',
    absolute_alpha_power: 1,
    relative_alpha_power: 0.1,
    individual_alpha_frequency_hz: null,
    iaf_confidence: 0,
    iaf_available: false,
    iaf_reason: 'no_reliable_alpha_peak',
    window_iaf_hz: null,
    window_iaf_confidence: null,
    alpha_trend: 'unavailable',
    alpha_trend_slope: null,
    alpha_change_from_baseline: null,
    drowsiness_score: null,
    state_confidence: 0,
    stimulation_demand: 0,
    demand_available: false,
    ready_to_remove: false,
    feature_provenance: 'derived',
    demand_provenance: 'SIMULATED CONTROL DEMAND — NOT ULTRASOUND DOSE',
  };
}

describe('Alpha replay timestamp and coverage diagnostics', () => {
  it('preserves recording-relative seconds and exact normalized EEG channel names', () => {
    const coverage = alphaAnalysisCoverage(descriptor());

    expect(coverage).toMatchObject({
      timestampUnit: 'seconds',
      analysisWindowSeconds: 30,
      stepSeconds: 10,
      firstFeatureTimeSeconds: 130,
      productDisplayContextSeconds: 300,
      channels: ['EEG Fpz-Cz', 'EEG Pz-Oz'],
    });
  });

  it('uses analysis-window end and handles cursor before, at, and after the first row', () => {
    const rows = [
      feature('EEG Fpz-Cz', 130),
      feature('EEG Pz-Oz', 130),
      feature('EEG Fpz-Cz', 140),
      feature('EEG Pz-Oz', 140),
    ];

    expect(reachedAlphaFeatureRows(rows, 129.999)).toHaveLength(0);
    expect(reachedAlphaFeatureRows(rows, 130)).toHaveLength(2);
    expect(reachedAlphaFeatureRows(rows, 140)).toHaveLength(4);
  });

  it('does not convert numeric seconds to milliseconds or compare timestamps as strings', () => {
    const rows = [feature('EEG Fpz-Cz', 158)];

    expect(reachedAlphaFeatureRows(rows, 157.5)).toHaveLength(0);
    expect(reachedAlphaFeatureRows(rows, 158)).toHaveLength(1);
    expect(reachedAlphaFeatureRows(rows, 157_500)).toHaveLength(1);
  });

  it('keeps weak IAF candidates out of the authoritative product state', () => {
    const row = feature('EEG Fpz-Cz', 130);
    row.iaf_available = true;
    row.individual_alpha_frequency_hz = 12.5;
    row.iaf_confidence = 0.398;

    expect(productIafIsReliable(row, alphaAnalysisCoverage(descriptor()))).toBe(
      false,
    );
    row.iaf_confidence = 0.5;
    expect(productIafIsReliable(row, alphaAnalysisCoverage(descriptor()))).toBe(
      true,
    );
  });

  it('is deterministic when seeking forward and backward across Wake and N1 rows', () => {
    const rows = [feature('EEG Fpz-Cz', 150), feature('EEG Fpz-Cz', 160)];

    expect(reachedAlphaFeatureRows(rows, 160).map((row) => row.stage)).toEqual([
      'W',
      'N1',
    ]);
    expect(reachedAlphaFeatureRows(rows, 155).map((row) => row.stage)).toEqual([
      'W',
    ]);
  });

  it('explains an empty bounded window before derived coverage without fabricating rows', () => {
    const coverage = alphaAnalysisCoverage(descriptor());

    expect(emptyAlphaWindowMessage(coverage, 125)).toContain(
      'precedes the first analysis-window end at 130.00 s',
    );
  });
});
