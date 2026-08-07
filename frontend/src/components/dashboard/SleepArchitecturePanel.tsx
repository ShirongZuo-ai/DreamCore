import { MoonStar } from 'lucide-react';

import { demoSleepStages } from '../../mocks/demoData';
import { PanelHeader } from '../common/PanelHeader';

const stageColors: Record<string, string> = {
  W: 'bg-[#6c7e90]',
  N1: 'bg-[#4b8ca4]',
  N2: 'bg-[#3db5d8]',
  N3: 'bg-[#28728c]',
  REM: 'bg-[#9b8cf4]',
};

export function SleepArchitecturePanel() {
  return (
    <section className="panel p-4 sm:p-5">
      <PanelHeader
        title="Sleep Architecture"
        eyebrow="Simulated summary"
        action={
          <MoonStar aria-hidden="true" className="text-accent" size={18} />
        }
      />
      <div
        className="mt-6 flex h-24 items-end gap-1"
        aria-label="Simulated sleep architecture bars"
      >
        {[42, 65, 81, 56, 92, 73, 62, 88, 49, 70, 85, 58, 77, 66].map(
          (height, index) => (
            <span
              key={`${height}-${index}`}
              className="min-w-0 flex-1 rounded-t-sm bg-accent/70"
              style={{
                height: `${height}%`,
                opacity: 0.45 + (index % 4) * 0.12,
              }}
            />
          ),
        )}
      </div>
      <div className="mt-4 grid grid-cols-4 gap-3 border-t border-line pt-4">
        {[
          ['Awake', '8%'],
          ['N1 / N2', '54%'],
          ['N3', '21%'],
          ['REM', '17%'],
        ].map(([label, value]) => (
          <div key={label}>
            <p className="text-[0.6875rem] text-secondary">{label}</p>
            <p className="mt-1 font-mono text-sm font-semibold text-primary">
              {value}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-4 text-[0.6875rem] leading-5 text-secondary">
        Demo distribution for layout validation. SWS is reported descriptively,
        not as a health score.
      </p>
    </section>
  );
}

export function SleepStageTimelinePanel() {
  return (
    <section className="panel p-4 sm:p-5">
      <PanelHeader
        title="Sleep Stage Timeline"
        eyebrow="Demo night structure"
      />
      <div
        className="mt-5 overflow-hidden rounded-control border border-line"
        aria-label="Simulated sleep stage timeline"
      >
        <div className="flex h-16">
          {demoSleepStages.map((segment, index) => (
            <span
              key={`${segment.stage}-${index}`}
              className={`grid min-w-0 place-items-center text-[0.625rem] font-semibold text-primary ${stageColors[segment.stage]}`}
              style={{ width: `${segment.width}%` }}
              title={`${segment.stage} simulated segment`}
            >
              {segment.width > 8 ? segment.stage : ''}
            </span>
          ))}
        </div>
      </div>
      <div className="mt-3 flex justify-between font-mono text-[0.625rem] text-secondary">
        <span>22:30</span>
        <span>00:30</span>
        <span>02:30</span>
        <span>04:30</span>
        <span>06:30</span>
      </div>
    </section>
  );
}
