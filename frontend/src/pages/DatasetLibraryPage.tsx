import {
  CheckCircle2,
  Database,
  Dices,
  Filter,
  FolderOpen,
  Play,
  Search,
  Shuffle,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { CapabilityStatus } from '../components/common/CapabilityStatus';
import { PanelHeader } from '../components/common/PanelHeader';
import { SessionCatalogTable } from '../components/datasets/SessionCatalogTable';
import { useSessionWorkspace } from '../hooks/useSessionWorkspace';
import {
  liveReplayEligibility,
  httpSessionCatalogService,
  sessionCatalogService,
  sessionMatchesFilter,
} from '../services/sessionCatalogService';
import type { CapabilityName, SessionManifest, SessionSummary } from '../types';

const capabilityFilters: { name: CapabilityName; label: string }[] = [
  { name: 'eeg', label: 'EEG' },
  { name: 'sleep_stage_labels', label: 'Sleep-stage labels' },
  { name: 'phase_estimation', label: 'Phase estimation' },
  { name: 'heart_rate', label: 'Heart rate' },
];

export function DatasetLibraryPage() {
  const navigate = useNavigate();
  const workspace = useSessionWorkspace();
  const datasets = workspace.catalog.datasets;
  const [query, setQuery] = useState('');
  const [datasetId, setDatasetId] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [recordingId, setRecordingId] = useState('');
  const [recordingPreview, setRecordingPreview] =
    useState<SessionManifest | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [requiredCapabilities, setRequiredCapabilities] = useState<
    CapabilityName[]
  >([...liveReplayEligibility.requiredCapabilities]);
  const [requireN3, setRequireN3] = useState(true);
  const [seed, setSeed] = useState(42);
  const [message, setMessage] = useState<string | null>(null);

  const candidates = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return workspace.catalog.sessions.filter((session) => {
      if (datasetId && session.dataset.id !== datasetId) return false;
      if (!normalized) return true;
      return [
        session.dataset.id,
        session.dataset.display_name,
        session.sessionId,
        session.subjectId,
        session.visitId ?? '',
      ]
        .join(' ')
        .toLocaleLowerCase()
        .includes(normalized);
    });
  }, [datasetId, query, workspace.catalog.sessions]);
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
  const subjects = useMemo(
    () =>
      [
        ...new Set(
          workspace.catalog.sessions
            .filter((session) => session.dataset.id === datasetId)
            .map((session) => session.subjectId),
        ),
      ].sort(),
    [datasetId, workspace.catalog.sessions],
  );
  const recordings = useMemo(
    () =>
      workspace.catalog.sessions.filter(
        (session) =>
          session.dataset.id === datasetId && session.subjectId === subjectId,
      ),
    [datasetId, subjectId, workspace.catalog.sessions],
  );

  useEffect(() => {
    const selected = workspace.selectedSession;
    if (!selected) {
      setRecordingPreview(null);
      setPreviewError(null);
      return;
    }
    let active = true;
    setRecordingPreview(null);
    setPreviewError(null);
    const service =
      selected.catalogTransport === 'http'
        ? httpSessionCatalogService
        : sessionCatalogService;
    void service
      .loadSession(selected.dataset.id, selected.sessionId)
      .then((manifest) => {
        if (active) setRecordingPreview(manifest);
      })
      .catch((error: unknown) => {
        if (active)
          setPreviewError(
            error instanceof Error ? error.message : 'Metadata unavailable',
          );
      });
    return () => {
      active = false;
    };
  }, [workspace.selectedSession]);

  function selectRecording(session: SessionSummary | null) {
    workspace.selectSession(session);
    if (session) {
      workspace.setDataSource(
        session.catalogTransport === 'http'
          ? 'real-public-dataset'
          : 'test-fixture',
      );
    }
  }

  function sourceCapabilityText(kind: 'eye' | 'alpha' | 'wake') {
    if (!recordingPreview) return 'Select a recording';
    const capabilities = recordingPreview.capabilities;
    if (kind === 'eye') {
      if (capabilities.eog.status !== 'AVAILABLE') return 'Not available';
      return capabilities.eye_movement_activity.status === 'AVAILABLE'
        ? 'Ready'
        : 'Analyzes automatically';
    }
    if (kind === 'alpha') {
      if (capabilities.eeg.status !== 'AVAILABLE') return 'Not available';
      return capabilities.alpha_power.status === 'AVAILABLE'
        ? 'Ready'
        : 'Analyzes automatically';
    }
    if (
      capabilities.eog.status !== 'AVAILABLE' ||
      capabilities.sleep_stage_labels.status !== 'AVAILABLE'
    )
      return 'Not available';
    return capabilities.eye_movement_activity.status === 'AVAILABLE'
      ? 'Ready to generate'
      : 'Analyzes automatically';
  }

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
      workspace.setDataSource(
        session.catalogTransport === 'http'
          ? 'real-public-dataset'
          : 'test-fixture',
      );
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
    if (!workspace.selectedSession) return;
    workspace.setDataSource(
      workspace.selectedSession.catalogTransport === 'http'
        ? 'real-public-dataset'
        : 'test-fixture',
    );
    const loaded = await workspace.loadSelectedSession();
    if (loaded) navigate('/live');
  }

  return (
    <div className="min-w-0 space-y-5" data-testid="datasets-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="eyebrow">Research data browser</p>
            <span className="demo-chip">Fixture + Real HTTP</span>
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

      <section aria-label="Local dataset collection">
        <div className="grid gap-3 lg:grid-cols-3">
          {datasets.map((dataset) => (
            <button
              type="button"
              key={dataset.id}
              data-testid={`dataset-card-${dataset.id}`}
              aria-pressed={datasetId === dataset.id}
              onClick={() => {
                setDatasetId(dataset.id);
                setSubjectId('');
                setRecordingId('');
                selectRecording(null);
              }}
              className={`panel min-h-44 p-4 text-left transition-colors ${
                datasetId === dataset.id
                  ? 'border-accent/60 bg-accent/5'
                  : 'hover:border-accent/30'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="eyebrow">{dataset.version ?? 'Unversioned'}</p>
                  <h2 className="mt-1 text-base font-semibold text-primary">
                    {dataset.display_name}
                  </h2>
                </div>
                {dataset.localStatus === 'available_locally' ? (
                  <CheckCircle2 className="text-accent" size={18} />
                ) : (
                  <FolderOpen className="text-secondary" size={18} />
                )}
              </div>
              <p className="mt-4 font-mono text-sm text-primary">
                {dataset.subjectCount} local subject
                {dataset.subjectCount === 1 ? '' : 's'} ·{' '}
                {dataset.localRecordingCount} recording
                {dataset.localRecordingCount === 1 ? '' : 's'}
              </p>
              <p className="mt-2 text-xs uppercase tracking-wide text-secondary">
                {dataset.signalModalities.length
                  ? dataset.signalModalities.join(' · ')
                  : 'Metadata catalog'}
              </p>
              <p className="mt-3 truncate text-[0.6875rem] text-secondary">
                {dataset.official_source ??
                  'DreamCore reproducible test fixture'}
              </p>
            </button>
          ))}
        </div>
      </section>

      <section className="panel p-4" aria-label="Recording selector">
        <PanelHeader
          eyebrow="Dataset → Subject → Recording"
          title="Open a recording"
        />
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <label className="text-xs text-secondary">
            Dataset
            <select
              aria-label="Dataset"
              value={datasetId}
              onChange={(event) => {
                setDatasetId(event.target.value);
                setSubjectId('');
                setRecordingId('');
                selectRecording(null);
              }}
              className="mt-1 min-h-11 w-full rounded-control border border-line bg-canvas px-3 text-sm text-primary"
            >
              <option value="">Choose dataset</option>
              {datasets.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {dataset.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-secondary">
            Subject
            <select
              aria-label="Subject"
              value={subjectId}
              disabled={!datasetId}
              onChange={(event) => {
                setSubjectId(event.target.value);
                setRecordingId('');
                selectRecording(null);
              }}
              className="mt-1 min-h-11 w-full rounded-control border border-line bg-canvas px-3 text-sm text-primary disabled:opacity-50"
            >
              <option value="">Choose subject</option>
              {subjects.map((subject) => (
                <option key={subject} value={subject}>
                  {subject}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-secondary">
            Recording
            <select
              aria-label="Recording"
              value={recordingId}
              disabled={!subjectId}
              onChange={(event) => {
                setRecordingId(event.target.value);
                selectRecording(
                  recordings.find(
                    (session) => session.sessionId === event.target.value,
                  ) ?? null,
                );
              }}
              className="mt-1 min-h-11 w-full rounded-control border border-line bg-canvas px-3 text-sm text-primary disabled:opacity-50"
            >
              <option value="">Choose recording</option>
              {recordings.map((recording) => (
                <option key={recording.sessionId} value={recording.sessionId}>
                  {recording.sessionId}
                </option>
              ))}
            </select>
          </label>
        </div>
        {recordingPreview ? (
          <div className="mt-4 grid gap-4 border-t border-line pt-4 lg:grid-cols-[1.2fr_1fr]">
            <div>
              <p className="metric-label">Recording metadata</p>
              <p className="mt-2 font-mono text-sm text-primary">
                Duration{' '}
                {(recordingPreview.recording.duration_seconds / 3600).toFixed(
                  2,
                )}{' '}
                h{' · '}rates{' '}
                {[
                  ...new Set(
                    recordingPreview.signals.map(
                      (signal) => signal.sampling_rate_hz,
                    ),
                  ),
                ]
                  .sort((left, right) => left - right)
                  .map((rate) => String(rate))
                  .join(', ')}{' '}
                Hz
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {recordingPreview.signals.map((signal) => (
                  <span
                    key={signal.id}
                    className="rounded-full border border-line px-2 py-1 font-mono text-[0.6875rem] text-secondary"
                  >
                    {signal.original_channel_name ?? signal.channel_name} ·{' '}
                    {signal.sampling_rate_hz} Hz
                  </span>
                ))}
              </div>
              <p className="mt-3 text-xs text-secondary">
                Annotation:{' '}
                {recordingPreview.annotations.sleep_stages?.available
                  ? 'Ready · official sleep stages'
                  : 'Not available'}
              </p>
            </div>
            <dl className="grid gap-2 text-xs">
              <div className="flex justify-between gap-3 border-b border-line/60 pb-2">
                <dt className="text-secondary">Eye Movement</dt>
                <dd className="text-right text-primary">
                  {sourceCapabilityText('eye')}
                </dd>
              </div>
              <div className="flex justify-between gap-3 border-b border-line/60 pb-2">
                <dt className="text-secondary">Alpha</dt>
                <dd className="text-right text-primary">
                  {sourceCapabilityText('alpha')}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-secondary">Wake Music</dt>
                <dd className="text-right text-primary">
                  {sourceCapabilityText('wake')}
                </dd>
              </div>
            </dl>
          </div>
        ) : null}
        {previewError ? (
          <p role="alert" className="mt-3 text-xs text-warning">
            {previewError}
          </p>
        ) : null}
      </section>

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
            Fixture and real public sources
          </p>
        </div>
        <div className="panel p-4">
          <p className="metric-label">Catalog Sessions</p>
          <p className="mt-2 font-mono text-2xl font-semibold text-primary">
            {workspace.catalog.sessions.length}
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
              <option value="">All datasets</option>
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
            workspace.setDataSource(
              session.catalogTransport === 'http'
                ? 'real-public-dataset'
                : 'test-fixture',
            );
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
            <Play aria-hidden="true" size={15} /> Open Viewer
          </button>
        </div>
      </section>

      <p className="flex items-center gap-2 text-xs text-secondary">
        <Database aria-hidden="true" size={14} /> Catalog metadata only · EEG is
        requested later as bounded windows
      </p>
      {workspace.catalog.error ? (
        <p role="alert" className="text-xs text-warning">
          Real Public Dataset transport unavailable · {workspace.catalog.error}
        </p>
      ) : null}
    </div>
  );
}
