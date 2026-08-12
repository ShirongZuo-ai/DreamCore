import { ShieldCheck } from 'lucide-react';

import type { LoadedSession, SafetyStatus } from '../../types';
import { PanelHeader } from '../common/PanelHeader';
import { StatusPill } from '../common/StatusPill';

export function SafetyPanel({
  status,
  session,
}: {
  status: SafetyStatus;
  session: LoadedSession;
}) {
  const isOfflineFixture = session.dataSource !== 'demo-simulation';
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
  const offlineRows = [
    ['Signal Integrity', 'Metadata only'],
    ['Electrode Contact', 'Unavailable'],
    ['Device Temperature', 'Unavailable'],
    ['Data Connection', 'Offline'],
    ['Navigation Alignment', 'Unavailable'],
    ['Automatic Stimulation', 'Disabled'],
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
      {isOfflineFixture ? (
        <div className="mt-3 rounded-control border border-warning/30 bg-warning/5 px-3 py-2.5">
          <p className="text-sm font-semibold text-warning">
            Offline session — no hardware telemetry
          </p>
          <p className="mt-1 text-xs text-secondary">
            {session.manifest.capabilities.hardware_telemetry.reason}
          </p>
        </div>
      ) : null}
      <dl className="mt-3 divide-y divide-line">
        {(isOfflineFixture ? offlineRows : rows).map((row) => (
          <div
            className="flex items-center justify-between gap-3 py-2.5"
            key={Array.isArray(row) ? row[0] : row.label}
          >
            <dt className="metric-label">
              {Array.isArray(row) ? row[0] : row.label}
            </dt>
            <dd>
              {Array.isArray(row) ? (
                <span className="text-xs font-medium text-secondary">
                  {row[1]}
                </span>
              ) : (
                <StatusPill tone={row.tone}>{row.value}</StatusPill>
              )}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 border-t border-line pt-3 text-[0.6875rem] leading-5 text-secondary">
        No hardware interlock or stimulation pathway is connected in this{' '}
        {isOfflineFixture ? 'offline fixture' : 'demo'}.
      </p>
    </section>
  );
}
