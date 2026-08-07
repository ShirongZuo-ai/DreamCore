import { FlaskConical } from 'lucide-react';

import { useSessionWorkspace } from '../../hooks/useSessionWorkspace';

export function DemoModeBadge() {
  const workspace = useSessionWorkspace();
  const loaded = workspace.loadState.session;
  const isReal = loaded?.realPublicData;
  const isFixture = loaded?.fixture;
  const label = isReal
    ? 'Real Public EEG'
    : isFixture
      ? 'Test Fixture'
      : 'Demo Mode';
  return (
    <span
      aria-label={
        isReal
          ? 'Real Public EEG Data: observed signals, derived metrics, simulated control'
          : isFixture
            ? 'Test Fixture: not real subject data'
            : 'Demo Mode: simulated data only'
      }
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-accent/30 bg-[var(--color-accent-muted)] px-2.5 py-1 text-[0.6875rem] font-semibold uppercase tracking-[0.1em] text-accent"
    >
      <FlaskConical aria-hidden="true" size={13} />
      <span className="hidden sm:inline">{label}</span>
      <span className="sm:hidden">
        {isReal ? 'Public EEG' : isFixture ? 'Fixture' : 'Demo'}
      </span>
    </span>
  );
}
