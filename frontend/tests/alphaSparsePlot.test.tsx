import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { UPlotTimeSeries } from '../src/components/charts/UPlotTimeSeries';

function renderSparse(values: readonly number[]) {
  render(
    <UPlotTimeSeries
      timestamps={values.map((_, index) => 30 + index * 30)}
      lines={[{ label: 'EEG O2-M1', values, stroke: '#3db5d8' }]}
      unit="µV²"
      height={150}
      maxPoints={100}
      testId="sparse-alpha"
      cursorTimestamp={90}
      xRange={[0, 120]}
      revealUntilTimestamp={90}
      showPoints
      connectPoints={false}
    />,
  );
  return screen.getByTestId('sparse-alpha');
}

describe('sparse Alpha feature visualization', () => {
  it('renders one valid feature row as a discrete observed glyph', () => {
    const chart = renderSparse([0.12]);
    expect(chart).toHaveAttribute('data-point-count', '1');
    expect(chart).toHaveAttribute('data-point-rendering', 'observed-glyphs');
    expect(chart).toHaveAttribute('data-point-connection', 'discrete');
  });

  it('renders two valid feature rows without inventing values between them', () => {
    const chart = renderSparse([0.12, 0.18]);
    expect(chart).toHaveAttribute('data-point-count', '2');
    expect(chart).toHaveAttribute('data-point-rendering', 'observed-glyphs');
    expect(chart).toHaveAttribute('data-point-connection', 'discrete');
  });
});
