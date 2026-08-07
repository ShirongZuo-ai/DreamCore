import { ArrowUpRight, Check } from 'lucide-react';
import { Link } from 'react-router-dom';

import type {
  CapabilityDescriptor,
  CapabilityStatus as CapabilityStatusType,
  SessionSummary,
} from '../../types';
import { CapabilityStatus } from '../common/CapabilityStatus';

function durationLabel(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes.toString().padStart(2, '0')}m`;
}

function aggregatePhysiology(session: SessionSummary): CapabilityDescriptor {
  const statuses = ['heart_rate', 'ppg', 'spo2', 'movement', 'snoring'].map(
    (name) =>
      session.capabilities[name as keyof typeof session.capabilities].status,
  );
  const status: CapabilityStatusType = statuses.includes('AVAILABLE')
    ? 'AVAILABLE'
    : statuses.includes('PLANNED')
      ? 'PLANNED'
      : statuses.includes('UNKNOWN')
        ? 'UNKNOWN'
        : 'UNAVAILABLE';
  return {
    status,
    source: 'unknown',
    reason: 'Aggregate of heart rate, PPG, SpO2, movement, and snoring',
  };
}

export function SessionCatalogTable({
  sessions,
  selected,
  onSelect,
  isValid,
}: {
  sessions: SessionSummary[];
  selected: SessionSummary | null;
  onSelect: (session: SessionSummary) => void;
  isValid: (session: SessionSummary) => boolean;
}) {
  if (sessions.length === 0) {
    return (
      <div className="px-5 py-12 text-center">
        <p className="text-sm font-medium text-primary">No sessions found</p>
        <p className="mt-1 text-xs text-secondary">
          Adjust the dataset or search query to restore catalog candidates.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="divide-y divide-line sm:hidden" aria-label="Session list">
        {sessions.map((session) => {
          const key = `${session.dataset.id}/${session.sessionId}`;
          const isSelected =
            selected?.dataset.id === session.dataset.id &&
            selected.sessionId === session.sessionId;
          return (
            <article
              key={key}
              className={isSelected ? 'bg-accent/10' : undefined}
              data-testid={`mobile-session-${session.sessionId}`}
            >
              <button
                type="button"
                onClick={() => onSelect(session)}
                className="w-full min-w-0 px-4 py-4 text-left"
              >
                <span className="flex min-w-0 items-start justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-sm font-semibold text-primary">
                      {session.sessionId}
                    </span>
                    <span className="mt-1 block truncate text-xs text-secondary">
                      {session.dataset.display_name} · {session.subjectId}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-xs text-secondary">
                    {durationLabel(session.durationSeconds)}
                  </span>
                </span>
                <span className="mt-3 grid grid-cols-3 gap-2">
                  {[
                    ['EEG', session.capabilities.eeg],
                    ['Stages', session.capabilities.sleep_stage_labels],
                    ['Phase', session.capabilities.phase_estimation],
                  ].map(([label, capability]) => (
                    <span className="min-w-0" key={label as string}>
                      <span className="block text-[0.625rem] uppercase tracking-wide text-secondary">
                        {label as string}
                      </span>
                      <CapabilityStatus
                        capability={capability as CapabilityDescriptor}
                      />
                    </span>
                  ))}
                </span>
              </button>
              <div className="flex items-center justify-between px-4 pb-3">
                <span
                  className={`text-xs ${isValid(session) ? 'text-success' : 'text-secondary'}`}
                >
                  {isValid(session) ? 'Valid for filter' : 'Does not match'}
                </span>
                <Link
                  to={`/datasets/${session.dataset.id}/sessions/${session.sessionId}`}
                  className="inline-flex items-center gap-1 text-xs text-accent"
                  aria-label={`View details for ${session.sessionId}`}
                >
                  Details <ArrowUpRight aria-hidden="true" size={13} />
                </Link>
              </div>
            </article>
          );
        })}
      </div>
      <div className="hidden w-full min-w-0 overflow-x-auto sm:block">
        <table className="w-full min-w-[68rem] text-left text-xs">
          <thead className="border-b border-line bg-elevated text-secondary">
            <tr>
              {[
                'Dataset',
                'Session',
                'Subject',
                'Duration',
                'EEG',
                'Sleep Stage',
                'SO',
                'Phase',
                'Precision',
                'Physiology',
                'Status',
                '',
              ].map((header) => (
                <th
                  className="whitespace-nowrap px-3 py-3 font-medium"
                  key={header}
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {sessions.map((session) => {
              const key = `${session.dataset.id}/${session.sessionId}`;
              const isSelected =
                selected?.dataset.id === session.dataset.id &&
                selected.sessionId === session.sessionId;
              return (
                <tr
                  key={key}
                  className={`cursor-pointer ${isSelected ? 'bg-accent/10' : 'hover:bg-elevated/60'}`}
                  onClick={() => onSelect(session)}
                  data-testid={`session-row-${session.sessionId}`}
                >
                  <td className="px-3 py-3 text-secondary">
                    {session.dataset.display_name}
                  </td>
                  <td className="px-3 py-3 font-mono font-semibold text-primary">
                    {session.sessionId}
                  </td>
                  <td className="px-3 py-3 font-mono text-secondary">
                    {session.subjectId}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 font-mono text-secondary">
                    {durationLabel(session.durationSeconds)}
                  </td>
                  {[
                    'eeg',
                    'sleep_stage_labels',
                    'slow_oscillation_detection',
                    'phase_estimation',
                    'phase_precision',
                  ].map((name) => (
                    <td className="px-3 py-3" key={name}>
                      <CapabilityStatus
                        compact
                        capability={
                          session.capabilities[
                            name as keyof typeof session.capabilities
                          ]
                        }
                      />
                    </td>
                  ))}
                  <td className="px-3 py-3">
                    <CapabilityStatus
                      compact
                      capability={aggregatePhysiology(session)}
                    />
                  </td>
                  <td className="px-3 py-3">
                    <span
                      className={`inline-flex items-center gap-1.5 whitespace-nowrap ${
                        isValid(session) ? 'text-success' : 'text-secondary'
                      }`}
                    >
                      {isValid(session) ? (
                        <Check aria-hidden="true" size={13} />
                      ) : null}
                      {isValid(session) ? 'Valid' : 'Does not match'}
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <Link
                      to={`/datasets/${session.dataset.id}/sessions/${session.sessionId}`}
                      onClick={(event) => event.stopPropagation()}
                      className="inline-flex items-center gap-1 text-accent"
                      aria-label={`View details for ${session.sessionId}`}
                    >
                      Details <ArrowUpRight aria-hidden="true" size={13} />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
