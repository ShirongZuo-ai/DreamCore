import { Flag } from 'lucide-react';

import type { TimelineEvent } from '../../types';
import { PanelHeader } from '../common/PanelHeader';

const lanes = [
  { label: 'Hypnogram', color: 'bg-accent', pattern: 'hypnogram' },
  {
    label: 'Stimulation Events',
    color: 'bg-stimulation',
    pattern: 'stimulation',
  },
  { label: 'Skipped Candidates', color: 'bg-warning', pattern: 'skipped' },
  { label: 'Artifacts', color: 'bg-danger', pattern: 'artifacts' },
  { label: 'Arousals', color: 'bg-[#d58c72]', pattern: 'arousals' },
  { label: 'Manual Markers', color: 'bg-primary', pattern: 'markers' },
] as const;

function LaneMarks({ pattern, color }: { pattern: string; color: string }) {
  const marks: Record<string, { left: string; width: string }[]> = {
    hypnogram: [
      { left: '1%', width: '13%' },
      { left: '17%', width: '22%' },
      { left: '42%', width: '18%' },
      { left: '64%', width: '28%' },
    ],
    stimulation: [
      { left: '28%', width: '0.4%' },
      { left: '71%', width: '0.4%' },
    ],
    skipped: [
      { left: '21%', width: '0.6%' },
      { left: '49%', width: '0.6%' },
      { left: '85%', width: '0.6%' },
    ],
    artifacts: [{ left: '54%', width: '7%' }],
    arousals: [{ left: '76%', width: '3%' }],
    markers: [{ left: '35%', width: '0.4%' }],
  };

  return (
    <>
      {marks[pattern].map((mark, index) => (
        <span
          className={`absolute inset-y-1 rounded-sm opacity-75 ${color}`}
          key={`${pattern}-${index}`}
          style={{ left: mark.left, width: mark.width }}
        />
      ))}
    </>
  );
}

export function SessionTimeline({
  events,
  showPlaceholders = true,
}: {
  events: TimelineEvent[];
  showPlaceholders?: boolean;
}) {
  return (
    <section className="panel overflow-hidden" aria-labelledby="timeline-title">
      <div className="flex items-center justify-between border-b border-line px-4 py-3.5">
        <PanelHeader
          title="Session Timeline"
          eyebrow="Structural placeholder"
          action={
            <span className="demo-chip">
              {showPlaceholders ? 'Demo' : 'Metadata only'}
            </span>
          }
        />
        <span className="hidden items-center gap-1.5 text-xs text-secondary sm:flex">
          <Flag aria-hidden="true" size={14} />
          {showPlaceholders
            ? `${events.length} example events`
            : 'No event payload loaded'}
        </span>
      </div>
      <div className="divide-y divide-line/70">
        {lanes.map((lane) => (
          <div
            className="grid grid-cols-[7.5rem_minmax(0,1fr)] items-center sm:grid-cols-[10rem_minmax(0,1fr)]"
            key={lane.label}
          >
            <div className="truncate px-3 py-2 text-[0.6875rem] text-secondary sm:px-4">
              {lane.label}
            </div>
            <div className="relative h-7 border-l border-line bg-[#111d2a]">
              {showPlaceholders ? (
                <LaneMarks pattern={lane.pattern} color={lane.color} />
              ) : null}
            </div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-[7.5rem_minmax(0,1fr)] border-t border-line bg-elevated sm:grid-cols-[10rem_minmax(0,1fr)]">
        <span />
        <div className="flex justify-between border-l border-line px-2 py-2 font-mono text-[0.625rem] text-secondary">
          <span>00:00</span>
          <span>02:00</span>
          <span>04:00</span>
          <span>06:00</span>
          <span>08:00</span>
        </div>
      </div>
    </section>
  );
}
