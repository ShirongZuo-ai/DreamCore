import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';

export type TimeSeriesLine = {
  label: string;
  values: readonly (number | null)[];
  stroke: string;
  dash?: number[];
};

export type TimeMarker = {
  id: string;
  timestamp: number;
  label: string;
  color: string;
  provenance: 'derived' | 'simulated' | 'sonification_control';
};

function timelinePosition(
  timestamp: number,
  start: number | undefined,
  end: number | undefined,
): string {
  if (start === undefined || end === undefined || end <= start) return '54px';
  const fraction = Math.max(
    0,
    Math.min(1, (timestamp - start) / (end - start)),
  );
  return `calc(54px + (100% - 62px) * ${fraction})`;
}

function downsampleIndices(length: number, maxPoints: number): number[] {
  if (length <= maxPoints) return Array.from({ length }, (_, index) => index);
  const step = (length - 1) / (maxPoints - 1);
  return Array.from({ length: maxPoints }, (_, index) =>
    Math.round(index * step),
  );
}

function visibleIndices(
  timestamps: readonly number[],
  start: number,
  end: number,
): number[] {
  const indices: number[] = [];
  for (let index = 0; index < timestamps.length; index += 1) {
    const timestamp = timestamps[index];
    if (timestamp >= start && timestamp <= end) indices.push(index);
  }
  return indices;
}

function downsampleIndexList(indices: number[], maxPoints: number): number[] {
  return downsampleIndices(indices.length, maxPoints).map(
    (index) => indices[index],
  );
}

function chartCursorLeft(chart: uPlot, timestamp: number): number {
  return chart.bbox.left / uPlot.pxRatio + chart.valToPos(timestamp, 'x');
}

export function UPlotTimeSeries({
  timestamps,
  lines,
  unit,
  height,
  maxPoints,
  testId,
  cursorTimestamp,
  xRange,
  revealUntilTimestamp,
  extendLastValueToCursor = false,
  markers = [],
  showMarkerLabels = false,
}: {
  timestamps: readonly number[];
  lines: readonly TimeSeriesLine[];
  unit: string;
  height: number;
  maxPoints: number;
  testId: string;
  cursorTimestamp?: number;
  xRange?: readonly [number, number];
  revealUntilTimestamp?: number;
  extendLastValueToCursor?: boolean;
  markers?: readonly TimeMarker[];
  showMarkerLabels?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<uPlot | null>(null);
  const linesRef = useRef(lines);
  const cursorTimestampRef = useRef(cursorTimestamp);
  linesRef.current = lines;
  cursorTimestampRef.current = cursorTimestamp;
  const seriesSignature = useMemo(
    () =>
      lines
        .map(
          (line) =>
            `${line.label}:${line.stroke}:${line.dash?.join(',') ?? ''}`,
        )
        .join('|'),
    [lines],
  );
  const xStart = xRange?.[0] ?? timestamps[0];
  const xEnd = xRange?.[1] ?? timestamps.at(-1);
  const revealEnd = Math.min(
    revealUntilTimestamp ?? xEnd ?? Number.POSITIVE_INFINITY,
    xEnd ?? Number.POSITIVE_INFINITY,
  );
  const lastVisibleTimestamp = useMemo(() => {
    if (xStart === undefined || xEnd === undefined) return undefined;
    for (let index = timestamps.length - 1; index >= 0; index -= 1) {
      const timestamp = timestamps[index];
      if (timestamp >= xStart && timestamp <= xEnd && timestamp <= revealEnd) {
        return timestamp;
      }
    }
    return undefined;
  }, [revealEnd, timestamps, xEnd, xStart]);

  useEffect(() => {
    const container = containerRef.current;
    if (
      !container ||
      timestamps.length === 0 ||
      navigator.userAgent.includes('jsdom')
    ) {
      return;
    }
    const initialLines = linesRef.current;
    const chart = new uPlot(
      {
        width: Math.max(container.clientWidth, 320),
        height,
        padding: [10, 8, 0, 0],
        cursor: { drag: { setScale: false } },
        legend: { show: false },
        scales: {
          x: {
            time: false,
            range:
              xStart !== undefined && xEnd !== undefined
                ? () => [xStart, xEnd]
                : undefined,
          },
        },
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
          ...initialLines.map((line) => ({
            label: line.label,
            stroke: line.stroke,
            width: 1.2,
            dash: line.dash,
            points: { show: false },
          })),
        ],
      },
      [[], ...initialLines.map(() => [])] as uPlot.AlignedData,
      container,
    );
    chartRef.current = chart;
    const initialCursorTimestamp = cursorTimestampRef.current;
    if (cursorRef.current && initialCursorTimestamp !== undefined) {
      cursorRef.current.style.left = `${chartCursorLeft(chart, initialCursorTimestamp)}px`;
    }
    const observer = new ResizeObserver(([entry]) => {
      chart.setSize({ width: Math.max(entry.contentRect.width, 320), height });
      const resizedCursorTimestamp = cursorTimestampRef.current;
      if (cursorRef.current && resizedCursorTimestamp !== undefined) {
        cursorRef.current.style.left = `${chartCursorLeft(chart, resizedCursorTimestamp)}px`;
      }
    });
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.destroy();
      chartRef.current = null;
    };
  }, [
    height,
    lines.length,
    seriesSignature,
    timestamps.length,
    unit,
    xEnd,
    xStart,
  ]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || timestamps.length === 0) return;
    const first = xStart ?? timestamps[0];
    if (first === undefined) return;
    const last = revealEnd;
    const indices = downsampleIndexList(
      visibleIndices(timestamps, first, last),
      maxPoints,
    );
    const xValues = indices.map((index) => timestamps[index]);
    const yValues = lines.map((line) =>
      indices.map((index) => line.values[index] ?? Number.NaN),
    );
    if (
      extendLastValueToCursor &&
      cursorTimestamp !== undefined &&
      cursorTimestamp >= first &&
      cursorTimestamp <= (xEnd ?? cursorTimestamp) &&
      xValues.length > 0 &&
      cursorTimestamp > xValues[xValues.length - 1]
    ) {
      xValues.push(cursorTimestamp);
      yValues.forEach((values, lineIndex) => {
        const source = lines[lineIndex].values;
        let heldValue = Number.NaN;
        for (let index = indices.length - 1; index >= 0; index -= 1) {
          const value = source[indices[index]];
          if (typeof value === 'number' && Number.isFinite(value)) {
            heldValue = value;
            break;
          }
        }
        values.push(heldValue);
      });
    }
    chart.setData([xValues, ...yValues] as uPlot.AlignedData);
  }, [
    cursorTimestamp,
    extendLastValueToCursor,
    lines,
    maxPoints,
    revealEnd,
    timestamps,
    xEnd,
    xStart,
  ]);

  useLayoutEffect(() => {
    const chart = chartRef.current;
    const cursor = cursorRef.current;
    if (!chart || !cursor || cursorTimestamp === undefined) return;
    cursor.style.left = `${chartCursorLeft(chart, cursorTimestamp)}px`;
    cursor.dataset.positionSource = 'uplot-valToPos-plus-bbox';
  }, [cursorTimestamp, xEnd, xStart]);

  const start = xStart;
  const end = xEnd;
  const visibleMarkers =
    start === undefined || end === undefined
      ? []
      : markers.filter(
          (marker) => marker.timestamp >= start && marker.timestamp <= end,
        );
  const cursorVisible =
    cursorTimestamp !== undefined &&
    start !== undefined &&
    end !== undefined &&
    cursorTimestamp >= start &&
    cursorTimestamp <= end;
  const displayEndTimestamp =
    extendLastValueToCursor &&
    lastVisibleTimestamp !== undefined &&
    cursorTimestamp !== undefined &&
    cursorTimestamp >= lastVisibleTimestamp
      ? cursorTimestamp
      : lastVisibleTimestamp;

  return (
    <div
      className="relative min-h-0 min-w-0 overflow-hidden"
      data-testid={testId}
      data-point-count={timestamps.length}
      data-last-visible-timestamp={lastVisibleTimestamp}
      data-display-end-timestamp={displayEndTimestamp}
      data-display-mode={
        extendLastValueToCursor
          ? 'stepwise-last-value-hold'
          : 'observed-samples'
      }
      data-reveal-until-timestamp={revealUntilTimestamp}
      aria-label={`${lines.map((line) => line.label).join(' and ')} time series in ${unit}`}
    >
      <div ref={containerRef} />
      {cursorVisible ? (
        <div
          ref={cursorRef}
          aria-label={`Offline replay cursor at ${cursorTimestamp.toFixed(2)} seconds`}
          className="pointer-events-none absolute bottom-[30px] top-[10px] z-10 w-px bg-white/70"
          data-testid={`${testId}-replay-cursor`}
          style={{ left: timelinePosition(cursorTimestamp, start, end) }}
        />
      ) : null}
      {visibleMarkers.map((marker) => (
        <div
          key={marker.id}
          aria-label={`${marker.label} at ${marker.timestamp.toFixed(2)} seconds`}
          className="pointer-events-none absolute bottom-[30px] top-[10px] z-20 w-0.5"
          data-provenance={marker.provenance}
          style={{
            left: timelinePosition(marker.timestamp, start, end),
            backgroundColor: marker.color,
          }}
          title={`${marker.label} · ${marker.timestamp.toFixed(2)} s`}
        >
          {showMarkerLabels ? (
            <span
              className="absolute left-1 top-0 whitespace-nowrap rounded px-1.5 py-0.5 font-mono text-[0.5625rem] font-semibold text-canvas"
              style={{ backgroundColor: marker.color }}
            >
              {marker.provenance === 'simulated' ? 'SIMULATED' : 'DERIVED'}
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
