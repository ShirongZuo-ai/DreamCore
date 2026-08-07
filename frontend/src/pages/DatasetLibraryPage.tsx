import { Database, Dices, Filter, Play, Search, Shuffle } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { CapabilityStatus } from '../components/common/CapabilityStatus';
import { PanelHeader } from '../components/common/PanelHeader';
import { SessionCatalogTable } from '../components/datasets/SessionCatalogTable';
import { useSessionWorkspace } from '../hooks/useSessionWorkspace';
import {
  liveReplayEligibility,
  sessionCatalogService,
  sessionMatchesFilter,
} from '../services/sessionCatalogService';
import type { CapabilityName } from '../types';

const capabilityFilters: { name: CapabilityName; label: string }[] = [
  { name: 'eeg', label: 'EEG' },
  { name: 'sleep_stage_labels', label: 'Sleep-stage labels' },
  { name: 'phase_estimation', label: 'Phase estimation' },
  { name: 'heart_rate', label: 'Heart rate' },
];

export function DatasetLibraryPage() {
  const navigate = useNavigate();
  const workspace = useSessionWorkspace();
  const datasets = sessionCatalogService.listDatasets();
  const [query, setQuery] = useState('');
  const [datasetId, setDatasetId] = useState('');
  const [requiredCapabilities, setRequiredCapabilities] = useState<
    CapabilityName[]
  >([...liveReplayEligibility.requiredCapabilities]);
  const [requireN3, setRequireN3] = useState(true);
  const [seed, setSeed] = useState(42);
  const [message, setMessage] = useState<string | null>(null);

  const candidates = useMemo(
    () => sessionCatalogService.searchSessions(query, datasetId || undefined),
    [datasetId, query],
  );
  const validFilter = useMemo(
    () => ({
      requiredCapabilities,
      optionalCapabilities: ['phase_precision'] as CapabilityName[],
      hasSleepStage:
        requiredCapabilities.includes('sleep_stage_labels') || undefined,
      hasN3: requireN3 || undefined,
    }),
    [requireN3, requiredCapabilities],
  );
  const validCount = candidates.filter((session) =>
    sessionMatchesFilter(session, validFilter),
  ).length;

  function chooseRandom(validOnly: boolean) {
    try {
      const session = validOnly
        ? sessionCatalogService.randomValidSession(
            candidates,
            validFilter,
            seed,
          )
        : sessionCatalogService.randomSession(candidates, seed);
      workspace.selectSession(session);
      workspace.setDataSource('offline-replay');
      setMessage(
        `${validOnly ? 'Random valid' : 'Random'} selection: ${session.sessionId}. Review before loading.`,
      );
      setSeed((value) => value + 1);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : 'Unable to select a session',
      );
    }
  }

  async function loadSession() {
    workspace.setDataSource('offline-replay');
    const loaded = await workspace.loadSelectedSession('offline-replay');
    if (loaded) navigate('/live');
  }

  return (
    <div className="min-w-0 space-y-5" data-testid="datasets-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="eyebrow">Research data browser</p>
            <span className="demo-chip">Test Fixtures</span>
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-primary">
            Dataset Library
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-secondary">
            Discover canonical Session Packages without loading signal payloads.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => chooseRandom(false)}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-control border border-line bg-elevated px-3 text-sm font-semibold text-primary hover:border-accent/50"
          >
            <Shuffle aria-hidden="true" size={15} /> Random Session
          </button>
          <button
            type="button"
            onClick={() => chooseRandom(true)}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-control border border-accent/40 bg-accent/10 px-3 text-sm font-semibold text-accent"
          >
            <Dices aria-hidden="true" size={15} /> Random Valid Session
          </button>
        </div>
      </div>

      <section
        className="grid gap-3 sm:grid-cols-3"
        aria-label="Dataset summary"
      >
        <div className="panel p-4">
          <p className="metric-label">Datasets</p>
          <p className="mt-2 font-mono text-2xl font-semibold text-primary">
            {datasets.length}
          </p>
          <p className="mt-1 text-[0.6875rem] text-secondary">
            TEST datasets only
          </p>
        </div>
        <div className="panel p-4">
          <p className="metric-label">Catalog Sessions</p>
          <p className="mt-2 font-mono text-2xl font-semibold text-primary">
            {sessionCatalogService.listSessions().length}
          </p>
          <p className="mt-1 text-[0.6875rem] text-secondary">
            Metadata, not signals
          </p>
        </div>
        <div className="panel p-4">
          <p className="metric-label">Valid for current filter</p>
          <p
            className="mt-2 font-mono text-2xl font-semibold text-accent"
            data-testid="valid-session-count"
          >
            {validCount}
          </p>
          <p className="mt-1 text-[0.6875rem] text-secondary">
            of {candidates.length} candidates
          </p>
        </div>
      </section>

      <section className="panel w-full max-w-full overflow-hidden">
        <div className="grid gap-4 border-b border-line p-4 lg:grid-cols-[minmax(15rem,1fr)_15rem]">
          <label className="relative block">
            <span className="sr-only">Search sessions</span>
            <Search
              aria-hidden="true"
              className="absolute left-3 top-3 text-secondary"
              size={16}
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search dataset, session, or TEST subject"
              className="min-h-10 w-full rounded-control border border-line bg-canvas pl-10 pr-3 text-sm text-primary placeholder:text-secondary focus:border-accent"
            />
          </label>
          <label>
            <span className="sr-only">Dataset filter</span>
            <select
              value={datasetId}
              onChange={(event) => setDatasetId(event.target.value)}
              className="min-h-10 w-full rounded-control border border-line bg-canvas px-3 text-sm text-primary"
            >
              <option value="">All test datasets</option>
              {datasets.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {dataset.display_name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
          <Filter
            aria-hidden="true"
            className="mr-1 text-secondary"
            size={15}
          />
          <span className="mr-2 text-xs text-secondary">
            Valid-session requirements
          </span>
          {capabilityFilters.map((item) => {
            const active = requiredCapabilities.includes(item.name);
            return (
              <button
                type="button"
                key={item.name}
                aria-pressed={active}
                onClick={() =>
                  setRequiredCapabilities((current) =>
                    active
                      ? current.filter((name) => name !== item.name)
                      : [...current, item.name],
                  )
                }
                className={`rounded-full border px-2.5 py-1 text-xs ${
                  active
                    ? 'border-accent/40 bg-accent/10 text-accent'
                    : 'border-line text-secondary'
                }`}
              >
                {item.label}
              </button>
            );
          })}
          <button
            type="button"
            aria-pressed={requireN3}
            onClick={() => setRequireN3((current) => !current)}
            className={`rounded-full border px-2.5 py-1 text-xs ${
              requireN3
                ? 'border-accent/40 bg-accent/10 text-accent'
                : 'border-line text-secondary'
            }`}
          >
            N3 present
          </button>
        </div>
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <PanelHeader
            title="Session Catalog"
            eyebrow={`${candidates.length} candidates`}
          />
          <span className="hidden text-xs text-secondary sm:inline">
            Seed {seed} · deterministic selection
          </span>
        </div>
        <SessionCatalogTable
          sessions={candidates}
          selected={workspace.selectedSession}
          onSelect={(session) => {
            workspace.selectSession(session);
            workspace.setDataSource('offline-replay');
            setMessage(`Selected ${session.sessionId}. No replay has started.`);
          }}
          isValid={(session) => sessionMatchesFilter(session, validFilter)}
        />
      </section>

      <section className="panel p-4" aria-label="Selected session">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <p className="eyebrow">Selected Session</p>
            {workspace.selectedSession ? (
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
                <p className="font-mono text-lg font-semibold text-primary">
                  {workspace.selectedSession.sessionId}
                </p>
                <span className="text-sm text-secondary">
                  {workspace.selectedSession.dataset.display_name}
                </span>
                <CapabilityStatus
                  capability={workspace.selectedSession.capabilities.eeg}
                />
              </div>
            ) : (
              <p className="mt-2 text-sm text-secondary">
                Select a catalog row or use a random-selection action.
              </p>
            )}
            {message ? (
              <p role="status" className="mt-2 text-xs text-secondary">
                {message}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            disabled={
              !workspace.selectedSession ||
              workspace.loadState.status === 'loading'
            }
            onClick={loadSession}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-control bg-accent px-4 text-sm font-semibold text-canvas disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Play aria-hidden="true" size={15} /> Load Session
          </button>
        </div>
      </section>

      <p className="flex items-center gap-2 text-xs text-secondary">
        <Database aria-hidden="true" size={14} /> Canonical metadata only · no
        EDF files or signal arrays loaded
      </p>
    </div>
  );
}
