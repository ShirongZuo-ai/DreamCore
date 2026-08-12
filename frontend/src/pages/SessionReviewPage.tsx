import { ArrowUpRight, Download, Filter, Target } from 'lucide-react';

import { PanelHeader } from '../components/common/PanelHeader';
import { StatusPill } from '../components/common/StatusPill';
import { ReviewMetric } from '../components/dashboard/ReviewMetric';
import {
  SleepArchitecturePanel,
  SleepStageTimelinePanel,
} from '../components/dashboard/SleepArchitecturePanel';
import { demoReviewMetrics } from '../mocks/demoData';

export function SessionReviewPage() {
  return (
    <div className="min-w-0 space-y-5" data-testid="review-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="eyebrow">Post-session analysis</p>
            <span className="demo-chip">Simulated</span>
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-primary">
            Session Review
          </h1>
          <p className="mt-1 text-sm text-secondary">
            DC-P012 · V01-S02 · Protocol B
          </p>
        </div>
        <button
          type="button"
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-control border border-line bg-elevated px-4 text-sm font-semibold text-primary hover:border-accent/50"
          aria-label="Export Session placeholder"
        >
          <Download aria-hidden="true" size={16} />
          Export Session
          <span className="text-[0.625rem] uppercase tracking-wide text-secondary">
            Demo
          </span>
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {demoReviewMetrics.map((metric) => (
          <ReviewMetric {...metric} key={metric.label} />
        ))}
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <SleepArchitecturePanel />
        <SleepStageTimelinePanel />
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[1.25fr_0.75fr]">
        <section className="panel p-4 sm:p-5">
          <PanelHeader
            title="Slow Oscillation Summary"
            eyebrow="Offline demo metrics"
            action={<StatusPill tone="accent">Simulated</StatusPill>}
          />
          <div className="mt-5 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
            {[
              ['Candidates', '284'],
              ['Eligible', '96'],
              ['Skipped', '188'],
              ['Valid windows', '91.2%'],
            ].map(([label, value]) => (
              <div key={label}>
                <p className="metric-label">{label}</p>
                <p className="mt-1 font-mono text-xl font-semibold text-primary">
                  {value}
                </p>
              </div>
            ))}
          </div>
          <div className="mt-6 border-t border-line pt-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-primary">
                  Candidate disposition
                </p>
                <p className="mt-1 text-xs text-secondary">
                  Illustrative proportions only
                </p>
              </div>
              <Filter aria-hidden="true" className="text-secondary" size={17} />
            </div>
            <div className="mt-4 flex h-3 overflow-hidden rounded-full bg-elevated">
              <span className="bg-accent" style={{ width: '34%' }} />
              <span className="bg-warning/80" style={{ width: '43%' }} />
              <span className="bg-[#6c7e90]" style={{ width: '23%' }} />
            </div>
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-[0.6875rem] text-secondary">
              <span>
                <i className="mr-1.5 inline-block size-2 rounded-full bg-accent" />
                Eligible
              </span>
              <span>
                <i className="mr-1.5 inline-block size-2 rounded-full bg-warning" />
                Confidence gate
              </span>
              <span>
                <i className="mr-1.5 inline-block size-2 rounded-full bg-[#6c7e90]" />
                Signal quality
              </span>
            </div>
          </div>
        </section>

        <section className="panel p-4 sm:p-5">
          <PanelHeader
            title="Phase Accuracy"
            eyebrow="Simulated distribution"
            action={
              <Target
                aria-hidden="true"
                className="text-stimulation"
                size={18}
              />
            }
          />
          <div
            className="mt-5 flex items-end gap-1.5"
            aria-label="Simulated phase accuracy histogram"
          >
            {[22, 38, 61, 84, 100, 89, 66, 43, 27, 16].map((height, index) => (
              <span
                key={`${height}-${index}`}
                className="h-28 flex-1 rounded-t-sm bg-stimulation/70"
                style={{ height: `${height}px` }}
              />
            ))}
          </div>
          <div className="mt-3 flex justify-between font-mono text-[0.625rem] text-secondary">
            <span>-90°</span>
            <span>0° target</span>
            <span>+90°</span>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-4 border-t border-line pt-4">
            <div>
              <p className="metric-label">Median error</p>
              <p className="metric-value">12.4°</p>
            </div>
            <div>
              <p className="metric-label">Within window</p>
              <p className="metric-value">87%</p>
            </div>
          </div>
        </section>
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[0.8fr_1.2fr]">
        <section className="panel p-4 sm:p-5">
          <PanelHeader title="Stimulation Events" eyebrow="Demo event ledger" />
          <div className="mt-4 space-y-1">
            {['01:18:42', '02:47:11', '04:06:38'].map((time, index) => (
              <div
                className="flex items-center justify-between border-t border-line py-3"
                key={time}
              >
                <div className="flex items-center gap-3">
                  <span className="size-2 rounded-full bg-stimulation" />
                  <div>
                    <p className="font-mono text-sm text-primary">{time}</p>
                    <p className="text-[0.6875rem] text-secondary">
                      Simulated event {index + 1}
                    </p>
                  </div>
                </div>
                <ArrowUpRight
                  aria-hidden="true"
                  className="text-secondary"
                  size={16}
                />
              </div>
            ))}
          </div>
        </section>

        <section className="panel overflow-hidden">
          <div className="border-b border-line p-4 sm:p-5">
            <PanelHeader
              title="Event Explorer"
              eyebrow="Static inspection table"
            />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-xs">
              <thead className="bg-elevated text-secondary">
                <tr>
                  {['Time', 'Event', 'Stage', 'Decision', 'Quality'].map(
                    (header) => (
                      <th className="px-4 py-3 font-medium" key={header}>
                        {header}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {[
                  ['01:18:42', 'Candidate', 'N3', 'Skipped', 'Fair'],
                  ['02:47:11', 'Demo event', 'N3', 'Logged', 'Good'],
                  ['04:06:38', 'Artifact', 'N2', 'Excluded', 'Poor'],
                ].map((row) => (
                  <tr key={row[0]}>
                    {row.map((cell, index) => (
                      <td
                        className={`px-4 py-3 ${index === 0 ? 'font-mono text-primary' : 'text-secondary'}`}
                        key={cell}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
