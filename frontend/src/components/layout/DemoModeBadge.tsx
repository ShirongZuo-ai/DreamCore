import { FlaskConical } from 'lucide-react';

export function DemoModeBadge() {
  return (
    <span
      aria-label="Demo Mode: simulated data only"
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-accent/30 bg-[var(--color-accent-muted)] px-2.5 py-1 text-[0.6875rem] font-semibold uppercase tracking-[0.1em] text-accent"
    >
      <FlaskConical aria-hidden="true" size={13} />
      <span className="hidden sm:inline">Demo Mode</span>
      <span className="sm:hidden">Demo</span>
    </span>
  );
}
