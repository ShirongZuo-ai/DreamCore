import { Dices, FolderOpen, Play, Shuffle } from 'lucide-react';
import { useMemo, useState } from 'react';

import { useSessionWorkspace } from '../../hooks/useSessionWorkspace';
import {
  liveReplayEligibility,
  sessionCatalogService,
} from '../../services/sessionCatalogService';
import type { DataSourceType } from '../../types';
import { CapabilityStatus } from '../common/CapabilityStatus';
import { PanelHeader } from '../common/PanelHeader';

export function SessionLoaderPanel() {
  const workspace = useSessionWorkspace();
  const datasets = sessionCatalogService.listDatasets();
  const sessions = sessionCatalogService.listSessions();
  const [datasetId, setDatasetId] = useState(
    workspace.selectedSession?.dataset.id ?? datasets[0]?.id ?? '',
  );
  const datasetSessions = useMemo(
    () => sessions.filter((session) => session.dataset.id === datasetId),
    [datasetId, sessions],
  );
  const [sessionId, setSessionId] = useState(
    workspace.selectedSession?.sessionId ?? datasetSessions[0]?.sessionId ?? '',
  );
  const [seed, setSeed] = useState(42);
  const [message, setMessage] = useState<string | null>(null);

  function selectFromControls() {
    const session = sessions.find(
      (item) => item.dataset.id === datasetId && item.sessionId === sessionId,
    );
    if (!session) {
      setMessage('Choose a TEST FIXTURE dataset and session.');
      return;
    }
    workspace.selectSession(session);
    workspace.setDataSource('offline-replay');
    setMessage(`Selected ${session.sessionId}. Loading has not started.`);
  }

  function chooseRandom(validOnly: boolean) {
    try {
      const selection = validOnly
        ? sessionCatalogService.randomValidSession(
            datasetSessions,
            liveReplayEligibility,
            seed,
          )
        : sessionCatalogService.randomSession(datasetSessions, seed);
      setSessionId(selection.sessionId);
      workspace.selectSession(selection);
      workspace.setDataSource('offline-replay');
      setMessage(
        `${validOnly ? 'Random valid' : 'Random'} selection: ${selection.sessionId}`,
      );
      setSeed((value) => value + 1);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : 'No candidate session',
      );
    }
  }

  async function load() {
    if (workspace.dataSource === 'demo-simulation') {
      workspace.loadDemoSimulation();
      setMessage('Demo Simulation loaded locally.');
      return;
    }
    const loaded = await workspace.loadSelectedSession('offline-replay');
    if (loaded)
      setMessage('TEST FIXTURE metadata loaded. Replay has not started.');
  }

  const loadedManifest = workspace.loadState.session?.manifest;

  return (
    <section className="panel overflow-hidden" aria-label="Session Loader">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <PanelHeader
          title="Session Loader"
          eyebrow="Source selection"
          action={
            <FolderOpen aria-hidden="true" size={17} className="text-accent" />
          }
        />
        <span className="hidden text-[0.6875rem] text-secondary sm:inline">
          Selection does not start replay
        </span>
      </div>
      <div className="grid gap-3 p-4 xl:grid-cols-[14rem_minmax(11rem,1fr)_minmax(10rem,1fr)_auto]">
        <label className="min-w-0">
          <span className="metric-label">Data Source</span>
          <select
            aria-label="Data Source"
            value={workspace.dataSource}
            onChange={(event) =>
              workspace.setDataSource(event.target.value as DataSourceType)
            }
            className="mt-1.5 min-h-10 w-full rounded-control border border-line bg-canvas px-3 text-sm text-primary"
          >
            <option value="demo-simulation">Demo Simulation</option>
            <option value="offline-replay">
              Offline Replay · Test Fixture
            </option>
            <option value="live-device" disabled>
              Live Device · Unavailable
            </option>
          </select>
        </label>
        <label className="min-w-0">
          <span className="metric-label">Dataset</span>
          <select
            aria-label="Dataset"
            value={datasetId}
            disabled={workspace.dataSource !== 'offline-replay'}
            onChange={(event) => {
              const nextDataset = event.target.value;
              const first = sessions.find(
                (session) => session.dataset.id === nextDataset,
              );
              setDatasetId(nextDataset);
              setSessionId(first?.sessionId ?? '');
            }}
            className="mt-1.5 min-h-10 w-full rounded-control border border-line bg-canvas px-3 text-sm text-primary disabled:opacity-45"
          >
            {datasets.map((dataset) => (
              <option value={dataset.id} key={dataset.id}>
                {dataset.display_name}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-0">
          <span className="metric-label">Session</span>
          <select
            aria-label="Session"
            value={sessionId}
            disabled={workspace.dataSource !== 'offline-replay'}
            onChange={(event) => setSessionId(event.target.value)}
            className="mt-1.5 min-h-10 w-full rounded-control border border-line bg-canvas px-3 font-mono text-sm text-primary disabled:opacity-45"
          >
            {datasetSessions.map((session) => (
              <option value={session.sessionId} key={session.sessionId}>
                {session.sessionId}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-end gap-2">
          <button
            type="button"
            disabled={workspace.dataSource !== 'offline-replay'}
            onClick={selectFromControls}
            className="min-h-10 rounded-control border border-line bg-elevated px-3 text-xs font-semibold text-primary disabled:opacity-40"
          >
            Select Session
          </button>
          <button
            type="button"
            disabled={workspace.dataSource !== 'offline-replay'}
            onClick={load}
            className="inline-flex min-h-10 items-center gap-1.5 rounded-control bg-accent px-3 text-xs font-semibold text-canvas disabled:opacity-40"
          >
            <Play aria-hidden="true" size={13} /> Load Session
          </button>
        </div>
      </div>
      <div className="flex flex-col gap-3 border-t border-line bg-elevated/50 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <p className="text-xs text-secondary">
            Loaded:{' '}
            <span className="font-mono font-semibold text-primary">
              {loadedManifest?.dataset.display_name} /{' '}
              {loadedManifest?.session.session_id}
            </span>
            {workspace.loadState.session?.fixture
              ? ' · TEST FIXTURE'
              : ' · Demo'}
          </p>
          {loadedManifest ? (
            <div
              className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1"
              aria-label="Loaded session capabilities"
            >
              {[
                { label: 'EEG', capability: loadedManifest.capabilities.eeg },
                {
                  label: 'Sleep stage',
                  capability: loadedManifest.capabilities.sleep_stage_labels,
                },
                {
                  label: 'Phase',
                  capability: loadedManifest.capabilities.phase_estimation,
                },
                {
                  label: 'Physiology',
                  capability: loadedManifest.capabilities.heart_rate,
                },
              ].map(({ label, capability }) => (
                <span className="inline-flex items-center gap-1.5" key={label}>
                  <span className="text-[0.6875rem] text-secondary">
                    {label}
                  </span>
                  <CapabilityStatus capability={capability} />
                </span>
              ))}
            </div>
          ) : null}
          {message || workspace.loadState.status === 'error' ? (
            <p role="status" className="mt-1 text-[0.6875rem] text-secondary">
              {workspace.loadState.status === 'error'
                ? workspace.loadState.error
                : message}
            </p>
          ) : null}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={workspace.dataSource !== 'offline-replay'}
            onClick={() => chooseRandom(false)}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-control border border-line px-2.5 text-xs text-primary disabled:opacity-40"
          >
            <Shuffle aria-hidden="true" size={13} /> Random Session
          </button>
          <button
            type="button"
            disabled={workspace.dataSource !== 'offline-replay'}
            onClick={() => chooseRandom(true)}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-control border border-accent/30 px-2.5 text-xs text-accent disabled:opacity-40"
          >
            <Dices aria-hidden="true" size={13} /> Random Valid Session
          </button>
        </div>
      </div>
    </section>
  );
}
