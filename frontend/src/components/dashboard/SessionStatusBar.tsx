import {
  Battery,
  Database,
  Radio,
  ShieldAlert,
  Timer,
  UserRound,
} from 'lucide-react';

import type { SubjectSession } from '../../types';

type SessionStatusItem = {
  label: string;
  value: string;
  icon: typeof Battery;
  tone?: 'warning' | 'success';
};

const statusItems = (session: SubjectSession): SessionStatusItem[] => [
  { label: 'Subject ID', value: session.subjectId, icon: UserRound },
  { label: 'Session ID', value: session.sessionId, icon: Radio },
  { label: 'Protocol Code', value: session.protocolCode, icon: ShieldAlert },
  { label: 'Recording Time', value: session.recordingTime, icon: Timer },
  { label: 'Device Status', value: 'Offline', icon: Radio, tone: 'warning' },
  { label: 'Data Latency', value: '—', icon: Timer },
  { label: 'Storage', value: 'Ready', icon: Database, tone: 'success' },
  { label: 'Battery', value: '—', icon: Battery },
];

export function SessionStatusBar({ session }: { session: SubjectSession }) {
  return (
    <section aria-label="Session status" className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="eyebrow">Session Status</span>
          <span className="demo-chip">Simulated</span>
        </div>
        <span className="font-mono text-[0.6875rem] text-secondary">
          LOCAL DEMO
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
