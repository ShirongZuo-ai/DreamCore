import type { ReactNode } from 'react';

type Tone =
  'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'stimulation';

const toneClasses: Record<Tone, string> = {
  neutral: 'border-line bg-elevated text-secondary',
  accent: 'border-accent/30 bg-[var(--color-accent-muted)] text-accent',
  success: 'border-success/30 bg-success/10 text-success',
  warning: 'border-warning/30 bg-warning/10 text-warning',
  danger: 'border-danger/30 bg-danger/10 text-danger',
  stimulation: 'border-stimulation/30 bg-stimulation/10 text-stimulation',
};

export function StatusPill({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: Tone;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}
