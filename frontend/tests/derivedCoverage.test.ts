import { describe, expect, it } from 'vitest';

import { coverageState, derivedCoverage } from '../src/lib/derivedCoverage';

describe('derived feature coverage', () => {
  it('keeps recording-relative seconds and never treats missing coverage as zero', () => {
    const coverage = derivedCoverage({
      available: true,
      source: 'derived',
      metadata: {
        coverage: {
          coverage_start_s: 4,
          coverage_end_s: 79500,
          window_s: 4,
          step_s: 1,
          row_count: 79497,
          source_channel: 'EOG horizontal',
        },
      },
    });

    expect(coverage?.coverageStartSeconds).toBe(4);
    expect(coverageState(coverage, 3.999)).toBe('outside_coverage');
    expect(coverageState(coverage, 4)).toBe('available');
    expect(coverageState(coverage, 157.5)).toBe('available');
    expect(coverageState(coverage, 157500)).toBe('outside_coverage');
    expect(coverageState(null, 0)).toBe('missing');
  });
});
