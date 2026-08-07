import { BrainCircuit, Clock3 } from 'lucide-react';

import type { ControllerDecision } from '../../types';
import { PanelHeader } from '../common/PanelHeader';
import { StatusPill } from '../common/StatusPill';

export function AIDecisionPanel({
  decision,
}: {
  decision: ControllerDecision;
}) {
  const rows = [
    { label: 'Sleep Stage', value: decision.sleepStage, detail: 'Simulated' },
    {
      label: 'Stage Confidence',
      value: `${Math.round(decision.stageConfidence * 100)}%`,
      detail: 'Demo',
    },
    { label: 'Slow Oscillation Phase', value: 'Waiting' },
    { label: 'Phase Precision', value: 'Waiting' },
    { label: 'Next Up-state', value: 'Not available' },
  ];

  return (
    <section className="panel p-4" aria-labelledby="ai-decision-title">
      <PanelHeader
        title="AI Decision"
        eyebrow="Research state"
        action={
          <BrainCircuit aria-hidden="true" className="text-accent" size={18} />
        }
      />
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-y border-line py-3">
        <div>
          <p className="metric-label">Controller State</p>
          <div className="mt-1.5">
            <StatusPill tone="accent">{decision.state}</StatusPill>
          </div>
        </div>
        <Clock3 aria-hidden="true" className="text-secondary" size={18} />
      </div>
      <dl className="divide-y divide-line">
        {rows.map((row) => (
          <div
            className="flex items-center justify-between gap-4 py-2.5"
            key={row.label}
          >
            <dt className="metric-label">{row.label}</dt>
            <dd className="text-right text-sm font-medium text-primary">
              {row.value}
              {row.detail ? (
                <span className="ml-2 text-[0.625rem] uppercase tracking-wide text-secondary">
                  {row.detail}
                </span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 rounded-control border border-line bg-elevated p-3">
        <div className="flex items-center justify-between gap-3">
          <span className="metric-label">Decision</span>
          <StatusPill tone="neutral">NO TRIGGER</StatusPill>
        </div>
        <p className="mt-2 text-sm font-medium text-primary">
          {decision.reason.label}
        </p>
      </div>
    </section>
  );
}
