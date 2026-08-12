import type { ContentDescriptor } from '../types';

export type DerivedCoverage = {
  coverageStartSeconds: number;
  coverageEndSeconds: number;
  windowSeconds: number;
  stepSeconds: number | null;
  rowCount: number;
  sourceChannel: string;
};

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function derivedCoverage(
  descriptor: ContentDescriptor | undefined,
): DerivedCoverage | null {
  const metadata = descriptor?.metadata;
  const raw = metadata?.coverage;
  if (!raw || typeof raw !== 'object') return null;
  const coverage = raw as Record<string, unknown>;
  const coverageStartSeconds = numberValue(coverage.coverage_start_s);
  const coverageEndSeconds = numberValue(coverage.coverage_end_s);
  const windowSeconds = numberValue(coverage.window_s);
  const stepSeconds = numberValue(coverage.step_s);
  const rowCount = numberValue(coverage.row_count);
  const sourceChannel = coverage.source_channel;
  if (
    coverageStartSeconds === null ||
    coverageEndSeconds === null ||
    windowSeconds === null ||
    rowCount === null ||
    typeof sourceChannel !== 'string'
  ) {
    return null;
  }
  return {
    coverageStartSeconds,
    coverageEndSeconds,
    windowSeconds,
    stepSeconds,
    rowCount,
    sourceChannel,
  };
}

export function coverageState(
  coverage: DerivedCoverage | null,
  currentTimeSeconds: number,
): 'available' | 'outside_coverage' | 'missing' {
  if (!coverage) return 'missing';
  return currentTimeSeconds >= coverage.coverageStartSeconds &&
    currentTimeSeconds <= coverage.coverageEndSeconds
    ? 'available'
    : 'outside_coverage';
}
