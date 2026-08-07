import { ShieldCheck } from 'lucide-react';

import type { SafetyStatus } from '../../types';
import { PanelHeader } from '../common/PanelHeader';
import { StatusPill } from '../common/StatusPill';

export function SafetyPanel({ status }: { status: SafetyStatus }) {
  const label = (value: string) =>
    value
      .split('-')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  const rows = [
    {
      label: 'Signal Integrity',
      value: label(status.signalIntegrity),
      tone: 'accent' as const,
    },
    {
      label: 'Electrode Contact',
      value: label(status.electrodeContact),
      tone: 'warning' as const,
    },
    {
      label: 'Device Temperature',
      value: 'Unavailable',
      tone: 'neutral' as const,
    },
    {
      label: 'Data Connection',
      value: label(status.dataConnection),
      tone: 'warning' as const,
    },
    {
      label: 'Navigation Alignment',
      value: label(status.navigationAlignment),
      tone: 'neutral' as const,
    },
    {
      label: 'Automatic Stimulation',
      value: label(status.automaticStimulation),
      tone: 'success' as const,
    },
  ];

  return (
    <section
      className="panel border-warning/30 p-4"
      aria-labelledby="safety-title"
    >
      <PanelHeader
        title="Safety"
        eyebrow="Always visible"
        action={
          <ShieldCheck aria-hidden="true" className="text-success" size={18} />
        }
      />
      <dl className="mt-3 divide-y divide-line">
        {rows.map((row) => (
          <div
            className="flex items-center justify-between gap-3 py-2.5"
            key={row.label}
          >
            <dt className="metric-label">{row.label}</dt>
            <dd>
              <StatusPill tone={row.tone}>{row.value}</StatusPill>
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 border-t border-line pt-3 text-[0.6875rem] leading-5 text-secondary">
        No hardware interlock or stimulation pathway is connected in this demo.
      </p>
    </section>
  );
}
