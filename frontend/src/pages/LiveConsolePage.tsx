import { AlertTriangle } from 'lucide-react';

import { AIDecisionPanel } from '../components/dashboard/AIDecisionPanel';
import { PhysiologyPanel } from '../components/dashboard/PhysiologyPanel';
import { SessionStatusBar } from '../components/dashboard/SessionStatusBar';
import { SessionTimeline } from '../components/dashboard/SessionTimeline';
import { EEGWaveformPanel } from '../components/eeg/EEGWaveformPanel';
import { EmergencyStopButton } from '../components/safety/EmergencyStopButton';
import { SafetyPanel } from '../components/safety/SafetyPanel';
import { useLocalEmergencyStop } from '../hooks/useLocalEmergencyStop';
import {
  demoDecision,
  demoEEGWindow,
  demoPhysiology,
  demoSafety,
  demoSession,
  demoTimelineEvents,
} from '../mocks/demoData';

export function LiveConsolePage() {
  const emergencyStop = useLocalEmergencyStop();

  return (
    <div className="min-w-0 space-y-4" data-testid="live-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="eyebrow">Operator workspace</p>
            <span className="demo-chip">Simulated</span>
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-primary">
            Live Console
          </h1>
          <p className="mt-1 text-sm text-secondary">
            Static research monitoring interface · no device connection
          </p>
        </div>
        <EmergencyStopButton
          isStopped={emergencyStop.isStopped}
          onActivate={emergencyStop.activate}
          onReset={emergencyStop.resetDemo}
        />
      </div>

      {emergencyStop.isStopped ? (
        <div
          role="status"
          className="flex items-start gap-3 rounded-card border border-danger/50 bg-danger/10 px-4 py-3 text-danger"
        >
          <AlertTriangle
            aria-hidden="true"
            className="mt-0.5 shrink-0"
            size={18}
          />
          <div>
            <p className="font-semibold">Local demo stop is active</p>
            <p className="mt-0.5 text-xs text-secondary">
              Only this interface state changed. No command was sent and no
              hardware is connected.
            </p>
          </div>
        </div>
      ) : null}

      <SessionStatusBar session={demoSession} />

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_21rem]">
        <EEGWaveformPanel window={demoEEGWindow} />
        <aside className="min-w-0" aria-label="AI decision panel">
          <AIDecisionPanel decision={demoDecision} />
        </aside>
      </div>

      <div className="grid min-w-0 items-start gap-4 lg:grid-cols-2">
        <SafetyPanel status={demoSafety} />
        <PhysiologyPanel snapshot={demoPhysiology} />
      </div>

      <SessionTimeline events={demoTimelineEvents} />
    </div>
  );
}
