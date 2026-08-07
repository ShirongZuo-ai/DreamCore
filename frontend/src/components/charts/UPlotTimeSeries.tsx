import { useEffect, useRef } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';

export type TimeSeriesLine = {
  label: string;
  values: readonly (number | null)[];
  stroke: string;
  dash?: number[];
};

function downsampleIndices(length: number, maxPoints: number): number[] {
  if (length <= maxPoints) return Array.from({ length }, (_, index) => index);
  const step = (length - 1) / (maxPoints - 1);
  return Array.from({ length: maxPoints }, (_, index) =>
    Math.round(index * step),
  );
}

export function UPlotTimeSeries({
  timestamps,
  lines,
  unit,
  height,
  maxPoints,
  testId,
}: {
  timestamps: readonly number[];
  lines: readonly TimeSeriesLine[];
  unit: string;
  height: number;
  maxPoints: number;
  testId: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (
      !container ||
      timestamps.length === 0 ||
      navigator.userAgent.includes('jsdom')
    ) {
      return;
    }
    const indices = downsampleIndices(timestamps.length, maxPoints);
    const data: uPlot.AlignedData = [
      indices.map((index) => timestamps[index]),
      ...lines.map((line) =>
        indices.map((index) => line.values[index] ?? Number.NaN),
      ),
    ];
    const chart = new uPlot(
      {
        width: Math.max(container.clientWidth, 320),
        height,
        padding: [10, 8, 0, 0],
        cursor: { drag: { setScale: false } },
        legend: { show: false },
        scales: { x: { time: false } },
        axes: [
          {
            stroke: '#91a4b7',
            grid: { stroke: '#2a3a4b', width: 1 },
            values: (_plot, ticks) =>
              ticks.map((value) => `${value.toFixed(0)} s`),
          },
          {
            stroke: '#91a4b7',
            grid: { stroke: '#2a3a4b', width: 1 },
            label: unit,
            size: 54,
          },
        ],
        series: [
          {},
          ...lines.map((line) => ({
            label: line.label,
            stroke: line.stroke,
            width: 1.2,
            dash: line.dash,
            points: { show: false },
          })),
        ],
      },
      data,
      container,
    );
    const observer = new ResizeObserver(([entry]) => {
      chart.setSize({ width: Math.max(entry.contentRect.width, 320), height });
    });
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.destroy();
    };
  }, [height, lines, maxPoints, timestamps, unit]);

  return (
    <div
      ref={containerRef}
      className="min-h-0 min-w-0 overflow-hidden"
      data-testid={testId}
      data-point-count={timestamps.length}
      aria-label={`${lines.map((line) => line.label).join(' and ')} time series in ${unit}`}
    />
  );
}
