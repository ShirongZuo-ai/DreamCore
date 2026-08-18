import { AlertTriangle } from 'lucide-react';

import { MissingDataState } from '../components/common/MissingDataState';
import { AlphaSessionViewer } from '../components/alpha/AlphaSessionViewer';
import { AIDecisionPanel } from '../components/dashboard/AIDecisionPanel';
import { PhysiologyPanel } from '../components/dashboard/PhysiologyPanel';
import { SessionLoaderPanel } from '../components/dashboard/SessionLoaderPanel';
import { SessionStatusBar } from '../components/dashboard/SessionStatusBar';
import { SessionTimeline } from '../components/dashboard/SessionTimeline';
import { EEGWaveformPanel } from '../components/eeg/EEGWaveformPanel';
import { EmergencyStopButton } from '../components/safety/EmergencyStopButton';
import { SafetyPanel } from '../components/safety/SafetyPanel';
import { useLocalEmergencyStop } from '../hooks/useLocalEmergencyStop';
import { useSessionWorkspace } from '../hooks/useSessionWorkspace';
import {
  demoDecision,
  demoEEGWindow,
  demoPhysiology,
  demoSafety,
  demoTimelineEvents,
} from '../mocks/demoData';

export function LiveConsolePage() {
  const emergencyStop = useLocalEmergencyStop();
  const workspace = useSessionWorkspace();
  const loadedSession = workspace.loadState.session;

  if (!loadedSession) {
    return (
      <div className="min-w-0 space-y-4" data-testid="live-page">
        <SessionLoaderPanel />
        <p className="panel p-5 text-sm text-secondary">
          No session is loaded. Choose Demo Simulation or a TEST FIXTURE
          session.
        </p>
      </div>
    );
  }

  const isDemo = loadedSession.dataSource === 'demo-simulation';
  const eegCapability = loadedSession.manifest.capabilities.eeg;

  if (loadedSession.realPublicData) {
    return (
      <div className="min-w-0 space-y-4" data-testid="live-page">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="eyebrow">Offline public-data workspace</p>
            <span className="demo-chip">REAL PUBLIC EEG / EOG DATA</span>
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-primary">
            Live Console
          </h1>
          <p className="mt-1 text-sm text-secondary">
            Offline replay sonification · real public EEG/EOG · no hardware
            connection
          </p>
        </div>
        <SessionLoaderPanel />
        <SessionStatusBar session={loadedSession} />
        {workspace.replaySource ? (
          <AlphaSessionViewer
            manifest={loadedSession.manifest}
            replaySource={workspace.replaySource}
          />
        ) : (
          <p className="panel p-5 text-sm text-secondary">
            ReplaySource unavailable.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-4" data-testid="live-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="eyebrow">Operator workspace</p>
            <span className="demo-chip">
              {loadedSession.fixture ? 'Test Fixture' : 'Simulated'}
            </span>
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-primary">
            Live Console
          </h1>
          <p className="mt-1 text-sm text-secondary">
            {loadedSession.fixture
              ? 'Offline Session Package metadata · replay not started'
              : 'Static research monitoring interface · no device connection'}
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

      <SessionLoaderPanel />

      <SessionStatusBar session={loadedSession} />

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_21rem]">
        {eegCapability.status === 'AVAILABLE' ? (
          <EEGWaveformPanel
            window={demoEEGWindow}
            sourceLabel={isDemo ? 'Simulated' : 'Static Fixture Placeholder'}
          />
        ) : (
          <section
            className="panel min-h-[29rem] p-4"
            aria-label="EEG unavailable"
          >
            <p className="eyebrow">Shared time axis</p>
            <h2 className="mt-1 text-base font-semibold text-primary">
              EEG Signal Monitor
            </h2>
            <div className="grid min-h-[23rem] place-items-center">
              <div className="max-w-md">
                <MissingDataState label="EEG" capability={eegCapability} />
                <p className="mt-3 text-center text-xs text-secondary">
                  No simulated waveform is substituted for a missing source
                  signal.
                </p>
              </div>
            </div>
          </section>
        )}
        <aside className="min-w-0" aria-label="AI decision panel">
          <AIDecisionPanel decision={demoDecision} session={loadedSession} />
        </aside>
      </div>

      <div className="grid min-w-0 items-start gap-4 lg:grid-cols-2">
        <SafetyPanel status={demoSafety} session={loadedSession} />
        <PhysiologyPanel snapshot={demoPhysiology} session={loadedSession} />
      </div>

      <SessionTimeline
        events={isDemo ? demoTimelineEvents : []}
        showPlaceholders={isDemo}
      />
    </div>
  );
}
