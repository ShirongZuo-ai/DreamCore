import { HeartPulse } from 'lucide-react';

import type {
  CapabilityDescriptor,
  LoadedSession,
  PhysiologySnapshot,
} from '../../types';
import { MissingDataState } from '../common/MissingDataState';
import { PanelHeader } from '../common/PanelHeader';

export function PhysiologyPanel({
  snapshot,
  session,
}: {
  snapshot: PhysiologySnapshot;
  session: LoadedSession;
}) {
  const isDemo = session.dataSource === 'demo-simulation';
  const metrics: {
    label: string;
    demoValue: string;
    capability: CapabilityDescriptor;
  }[] = [
    {
      label: 'Heart Rate',
      demoValue: `${snapshot.heartRateBpm} bpm`,
      capability: session.manifest.capabilities.heart_rate,
    },
    {
      label: 'SpO₂',
      demoValue: `${snapshot.spo2Percent}%`,
      capability: session.manifest.capabilities.spo2,
    },
    {
      label: 'Movement',
      demoValue: 'Low',
      capability: session.manifest.capabilities.movement,
    },
    {
      label: 'Snoring',
      demoValue: 'None detected',
      capability: session.manifest.capabilities.snoring,
    },
  ];

  return (
    <section className="panel p-4" aria-labelledby="physiology-title">
      <PanelHeader
        title="Physiology"
        eyebrow={isDemo ? 'Simulated signals' : 'Session capabilities'}
        action={
          <HeartPulse aria-hidden="true" className="text-accent" size={18} />
        }
      />
      <dl className="mt-3 grid grid-cols-2 gap-x-4">
        {metrics.map((metric) => (
          <div className="border-t border-line py-3" key={metric.label}>
            <dt className="metric-label">{metric.label}</dt>
            {isDemo ? (
              <>
                <dd className="metric-value">{metric.demoValue}</dd>
                <span className="mt-1 block text-[0.625rem] uppercase tracking-wide text-secondary">
                  Simulated
                </span>
              </>
            ) : metric.capability.status === 'AVAILABLE' ? (
              <dd className="mt-1">
                <p className="text-sm font-semibold text-success">
                  Signal available
                </p>
                <p className="mt-1 text-[0.6875rem] text-secondary">
                  {metric.capability.source} metadata · no replay value loaded
                </p>
              </dd>
            ) : (
              <dd className="mt-1">
                <MissingDataState
                  compact
                  label={metric.label}
                  capability={{
                    ...metric.capability,
                    reason:
                      metric.capability.reason ?? 'Unavailable in this session',
                  }}
                />
              </dd>
            )}
          </div>
        ))}
      </dl>
    </section>
  );
}
