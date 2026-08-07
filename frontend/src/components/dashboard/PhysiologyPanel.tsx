import { HeartPulse } from 'lucide-react';

import type { PhysiologySnapshot } from '../../types';
import { PanelHeader } from '../common/PanelHeader';

export function PhysiologyPanel({
  snapshot,
}: {
  snapshot: PhysiologySnapshot;
}) {
  const metrics = [
    { label: 'Heart Rate', value: `${snapshot.heartRateBpm} bpm` },
    { label: 'SpO₂', value: `${snapshot.spo2Percent}%` },
    { label: 'Movement', value: 'Low' },
    { label: 'Snoring', value: 'None detected' },
  ];

  return (
    <section className="panel p-4" aria-labelledby="physiology-title">
      <PanelHeader
        title="Physiology"
        eyebrow="Simulated signals"
        action={
          <HeartPulse aria-hidden="true" className="text-accent" size={18} />
        }
      />
      <dl className="mt-3 grid grid-cols-2 gap-x-4">
        {metrics.map((metric) => (
          <div className="border-t border-line py-3" key={metric.label}>
            <dt className="metric-label">{metric.label}</dt>
            <dd className="metric-value">{metric.value}</dd>
            <span className="mt-1 block text-[0.625rem] uppercase tracking-wide text-secondary">
              Simulated
            </span>
          </div>
        ))}
      </dl>
    </section>
  );
}
