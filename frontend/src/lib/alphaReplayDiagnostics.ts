import type { AlphaFeatureRecord, ContentDescriptor } from '../types';

export type AlphaAnalysisCoverage = {
  timeReference: 'recording_relative';
  timestampField: 'window_end_s';
  timestampUnit: 'seconds';
  evaluationStartSeconds: number;
  evaluationEndSeconds: number;
  analysisWindowSeconds: number;
  stepSeconds: number;
  attemptedWindows: number;
  acceptedWindows: number;
  rejectedWindows: number;
  rejectionReasons: Record<string, number>;
  featureRowCount: number;
  firstFeatureTimeSeconds: number | null;
  lastFeatureTimeSeconds: number | null;
  channels: string[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function finiteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function nullableFiniteNumber(value: unknown): value is number | null {
  return value === null || finiteNumber(value);
}

export function alphaAnalysisCoverage(
  descriptor: ContentDescriptor | undefined,
): AlphaAnalysisCoverage | null {
  const raw = descriptor?.metadata?.analysis;
  if (!isRecord(raw) || !isRecord(raw.rejection_reasons)) return null;
  if (
    raw.time_reference !== 'recording_relative' ||
    raw.timestamp_field !== 'window_end_s' ||
    raw.timestamp_unit !== 'seconds' ||
    !finiteNumber(raw.evaluation_start_s) ||
    !finiteNumber(raw.evaluation_end_s) ||
    !finiteNumber(raw.analysis_window_s) ||
    !finiteNumber(raw.step_s) ||
    !finiteNumber(raw.attempted_windows) ||
    !finiteNumber(raw.accepted_windows) ||
    !finiteNumber(raw.rejected_windows) ||
    !finiteNumber(raw.feature_row_count) ||
    !nullableFiniteNumber(raw.first_feature_time_s) ||
    !nullableFiniteNumber(raw.last_feature_time_s) ||
    !Array.isArray(raw.channels) ||
    !raw.channels.every((channel) => typeof channel === 'string') ||
    !Object.values(raw.rejection_reasons).every(finiteNumber)
  ) {
    return null;
  }
  return {
    timeReference: raw.time_reference,
    timestampField: raw.timestamp_field,
    timestampUnit: raw.timestamp_unit,
    evaluationStartSeconds: raw.evaluation_start_s,
    evaluationEndSeconds: raw.evaluation_end_s,
    analysisWindowSeconds: raw.analysis_window_s,
    stepSeconds: raw.step_s,
    attemptedWindows: raw.attempted_windows,
    acceptedWindows: raw.accepted_windows,
    rejectedWindows: raw.rejected_windows,
    rejectionReasons: raw.rejection_reasons as Record<string, number>,
    featureRowCount: raw.feature_row_count,
    firstFeatureTimeSeconds: raw.first_feature_time_s,
    lastFeatureTimeSeconds: raw.last_feature_time_s,
    channels: [...raw.channels],
  };
}

export function reachedAlphaFeatureRows(
  rows: readonly AlphaFeatureRecord[],
  currentTimeSeconds: number,
) {
  return rows.filter((row) => row.window_end_s <= currentTimeSeconds);
}

export function emptyAlphaWindowMessage(
  coverage: AlphaAnalysisCoverage | null,
  currentTimeSeconds: number,
) {
  if (!coverage) return 'Not computed / unavailable in this window.';
  if (coverage.featureRowCount === 0) {
    return 'DreamCore Alpha extraction produced no feature rows for this session.';
  }
  if (
    coverage.firstFeatureTimeSeconds !== null &&
    currentTimeSeconds < coverage.firstFeatureTimeSeconds
  ) {
    return `No Alpha row is expected yet. Cursor ${currentTimeSeconds.toFixed(2)} s precedes the first analysis-window end at ${coverage.firstFeatureTimeSeconds.toFixed(2)} s.`;
  }
  if (
    coverage.lastFeatureTimeSeconds !== null &&
    currentTimeSeconds > coverage.lastFeatureTimeSeconds
  ) {
    return `Cursor ${currentTimeSeconds.toFixed(2)} s is after the last precomputed Alpha row at ${coverage.lastFeatureTimeSeconds.toFixed(2)} s.`;
  }
  return 'No stage-pure Alpha feature row is stored in this bounded window.';
}
