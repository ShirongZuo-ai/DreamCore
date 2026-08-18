import {
  Battery,
  Database,
  Radio,
  ShieldAlert,
  Timer,
  UserRound,
} from 'lucide-react';

import type { LoadedSession } from '../../types';

type SessionStatusItem = {
  label: string;
  value: string;
  icon: typeof Battery;
  tone?: 'warning' | 'success';
};

function durationLabel(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:00`;
}

const statusItems = (loaded: LoadedSession): SessionStatusItem[] => {
  const { manifest } = loaded;
  return [
    { label: 'Dataset', value: manifest.dataset.display_name, icon: Database },
    { label: 'Session ID', value: manifest.session.session_id, icon: Radio },
    {
      label: 'Subject ID',
      value: manifest.session.subject_id,
      icon: UserRound,
    },
    {
      label: 'Duration',
      value: durationLabel(manifest.recording.duration_seconds),
      icon: Timer,
    },
    {
      label: 'Data Source',
      value: loaded.realPublicData
        ? 'Real Public Dataset'
        : loaded.fixture
          ? 'Test Fixture'
          : 'Demo Simulation',
      icon: ShieldAlert,
    },
    {
      label: 'Replay State',
      value: loaded.realPublicData ? 'Offline simulation' : 'Not started',
      icon: Timer,
    },
    { label: 'Metadata', value: 'Ready', icon: Database, tone: 'success' },
    { label: 'Hardware', value: 'Offline', icon: Battery, tone: 'warning' },
  ];
};

export function SessionStatusBar({ session }: { session: LoadedSession }) {
  return (
    <section aria-label="Session status" className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="eyebrow">Session Status</span>
          <span className="demo-chip">
            {session.realPublicData
              ? 'Observed + Derived + Simulated'
              : session.fixture
                ? 'Test Fixture'
                : 'Simulated'}
          </span>
        </div>
        <span className="font-mono text-[0.6875rem] text-secondary">
          {session.dataSource.replaceAll('-', ' ').toUpperCase()}
        </span>
      </div>
      <dl className="grid grid-cols-2 divide-x-0 divide-y divide-line sm:grid-cols-4 xl:grid-cols-8 xl:divide-x xl:divide-y-0">
        {statusItems(session).map(({ label, value, icon: Icon, tone }) => (
          <div className="min-w-0 px-3 py-3 xl:px-4" key={label}>
            <dt className="flex items-center gap-1.5 text-[0.6875rem] text-secondary">
              <Icon aria-hidden="true" size={12} />
              {label}
            </dt>
            <dd
              className={`mt-1 truncate font-mono text-sm font-semibold ${
                tone === 'warning'
                  ? 'text-warning'
                  : tone === 'success'
                    ? 'text-success'
                    : 'text-primary'
              }`}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
