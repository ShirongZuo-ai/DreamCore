import { BrainCircuit, Clock3 } from 'lucide-react';

import type { ControllerDecision, LoadedSession } from '../../types';
import { CapabilityStatus } from '../common/CapabilityStatus';
import { PanelHeader } from '../common/PanelHeader';
import { StatusPill } from '../common/StatusPill';

export function AIDecisionPanel({
  decision,
  session,
}: {
  decision: ControllerDecision;
  session: LoadedSession;
}) {
  const isDemo = session.dataSource === 'demo-simulation';
  const { capabilities } = session.manifest;

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
            <StatusPill tone={isDemo ? 'accent' : 'neutral'}>
              {isDemo ? decision.state : 'IDLE'}
            </StatusPill>
          </div>
        </div>
        <Clock3 aria-hidden="true" className="text-secondary" size={18} />
      </div>
      <dl className="divide-y divide-line">
        <div className="flex items-center justify-between gap-4 py-2.5">
          <dt className="metric-label">Sleep Stage</dt>
          <dd className="text-right text-sm font-medium text-primary">
            {isDemo ? (
              <>
                {decision.sleepStage}
                <span className="ml-2 text-[0.625rem] uppercase text-secondary">
                  Simulated
                </span>
              </>
            ) : capabilities.sleep_stage_predictions.status === 'AVAILABLE' ? (
              <CapabilityStatus
                capability={capabilities.sleep_stage_predictions}
              />
            ) : capabilities.sleep_stage_labels.status === 'AVAILABLE' ? (
              <span>
                Labels available
                <span className="ml-2 text-[0.625rem] uppercase text-secondary">
                  Offline
                </span>
              </span>
            ) : (
              <CapabilityStatus
                capability={capabilities.sleep_stage_predictions}
              />
            )}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-4 py-2.5">
          <dt className="metric-label">Stage Confidence</dt>
          <dd className="text-right text-sm font-medium text-primary">
            {isDemo
              ? `${Math.round(decision.stageConfidence * 100)}%`
              : 'Not computed'}
          </dd>
        </div>
        {[
          ['Slow Oscillation', capabilities.slow_oscillation_detection],
          ['Phase Estimation', capabilities.phase_estimation],
          ['Phase Precision', capabilities.phase_precision],
        ].map(([label, item]) => (
          <div
            className="flex items-center justify-between gap-4 py-2.5"
            key={label as string}
          >
            <dt className="metric-label">{label as string}</dt>
            <dd className="text-right">
              {isDemo ? (
                <span className="text-sm font-medium text-primary">
                  Waiting
                </span>
              ) : (
                <CapabilityStatus
                  capability={item as typeof capabilities.phase_estimation}
                />
              )}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 rounded-control border border-line bg-elevated p-3">
        <div className="flex items-center justify-between gap-3">
          <span className="metric-label">Decision</span>
          {isDemo ? (
            <StatusPill tone="neutral">NO TRIGGER</StatusPill>
          ) : (
            <CapabilityStatus capability={capabilities.decision_simulation} />
          )}
        </div>
        <p className="mt-2 text-sm font-medium text-primary">
          {isDemo
            ? decision.reason.label
            : (capabilities.decision_simulation.reason ??
              'No decision output for this session')}
        </p>
      </div>
    </section>
  );
}
