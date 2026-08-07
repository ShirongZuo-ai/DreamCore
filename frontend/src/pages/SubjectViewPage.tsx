import {
  BellRing,
  Check,
  CircleDot,
  Headphones,
  HelpCircle,
  Leaf,
} from 'lucide-react';
import { useState } from 'react';

const steps = [
  {
    label: 'Device Fitting',
    detail: 'Fitting check complete',
    icon: Headphones,
    state: 'complete',
  },
  {
    label: 'Electrode Contact',
    detail: 'Waiting for device connection',
    icon: CircleDot,
    state: 'waiting',
  },
  {
    label: 'Recording Status',
    detail: 'Demo session ready',
    icon: BellRing,
    state: 'ready',
  },
] as const;

export function SubjectViewPage() {
  const [assistanceRequested, setAssistanceRequested] = useState(false);

  return (
    <div
      className="mx-auto flex min-h-[calc(100vh-8.5rem)] w-full max-w-5xl flex-col justify-center"
      data-testid="subject-page"
    >
      <div className="mb-8 text-center">
        <span className="demo-chip">Demonstration</span>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-primary sm:text-3xl">
          Everything is ready for your session
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-secondary">
          Settle into a comfortable position. The research team will manage the
          session from here.
        </p>
      </div>

      <section className="panel overflow-hidden" aria-label="Session readiness">
        <div className="grid divide-y divide-line md:grid-cols-3 md:divide-x md:divide-y-0">
          {steps.map(({ label, detail, icon: Icon, state }) => (
            <div className="flex items-start gap-4 p-5 sm:p-6" key={label}>
              <span
                className={`grid size-10 shrink-0 place-items-center rounded-full border ${state === 'complete' ? 'border-success/40 bg-success/10 text-success' : 'border-line bg-elevated text-accent'}`}
              >
                {state === 'complete' ? (
                  <Check aria-hidden="true" size={18} />
                ) : (
                  <Icon aria-hidden="true" size={18} />
                )}
              </span>
              <div>
                <p className="text-sm font-semibold text-primary">{label}</p>
                <p className="mt-1 text-xs leading-5 text-secondary">
                  {detail}
                </p>
                <span className="mt-2 block text-[0.625rem] uppercase tracking-[0.1em] text-secondary">
                  Demo status
                </span>
              </div>
            </div>
          ))}
        </div>

        <div className="border-t border-line p-5 sm:p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-primary">
                Session Progress
              </p>
              <p className="mt-1 text-xs text-secondary">Preparation · Demo</p>
            </div>
            <span className="font-mono text-sm font-semibold text-accent">
              18%
            </span>
          </div>
          <div
            className="mt-3 h-2 overflow-hidden rounded-full bg-elevated"
            aria-label="Demo session progress: 18 percent"
          >
            <div className="h-full w-[18%] rounded-full bg-accent" />
          </div>
        </div>
      </section>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <section className="panel flex items-center gap-4 p-5">
          <span className="grid size-10 shrink-0 place-items-center rounded-full border border-success/30 bg-success/10 text-success">
            <Leaf aria-hidden="true" size={18} />
          </span>
          <div>
            <p className="text-sm font-semibold text-primary">
              Environmental Comfort
            </p>
            <p className="mt-1 text-xs text-secondary">
              Room conditions marked comfortable · Demo
            </p>
          </div>
        </section>

        <button
          type="button"
          className="panel flex min-h-20 items-center gap-4 p-5 text-left hover:border-accent/50"
          onClick={() => setAssistanceRequested(true)}
          aria-label="Request Assistance — local demo only"
        >
          <span className="grid size-10 shrink-0 place-items-center rounded-full border border-accent/30 bg-accent/10 text-accent">
            <HelpCircle aria-hidden="true" size={18} />
          </span>
          <span>
            <span className="block text-sm font-semibold text-primary">
              Request Assistance
            </span>
            <span className="mt-1 block text-xs text-secondary">
              Notify the research team in this demo
            </span>
          </span>
        </button>
      </div>

      {assistanceRequested ? (
        <div
          role="status"
          className="mt-4 rounded-card border border-accent/30 bg-accent/10 px-4 py-3 text-center text-sm text-primary"
        >
          Demo request noted locally. No external message was sent.
        </div>
      ) : null}
    </div>
  );
}
