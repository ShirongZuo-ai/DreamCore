import { ChevronLeft, ChevronRight, LocateFixed, Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  eogValidationApi,
  type FilteredValidationWindow,
  type FocusResponse,
  type ReviewProgress,
  type ValidationRecording,
  type ValidationSample,
} from '../../services/eogValidationApi';
import { UPlotTimeSeries } from '../charts/UPlotTimeSeries';

type ReviewKind = 'candidate' | 'control';
type ValidationTab = ReviewKind | 'agreement' | 'stages' | 'progress';

const candidateLabels = [
  'Likely Eye Movement',
  'Artifact / Non-eye-movement',
  'Uncertain',
];
const controlLabels = [
  'No obvious eye movement',
  'Possible missed eye movement',
  'Artifact / unusable',
  'Uncertain',
];

export function EogValidationPanel({
  sessionId,
  onFocus,
}: {
  sessionId: string;
  onFocus: (
    startSeconds: number,
    endSeconds: number,
    timestamp: number,
  ) => void;
}) {
  const [recording, setRecording] = useState<ValidationRecording | null>(null);
  const [candidates, setCandidates] = useState<ValidationSample[]>([]);
  const [controls, setControls] = useState<ValidationSample[]>([]);
  const [progress, setProgress] = useState<ReviewProgress | null>(null);
  const [tab, setTab] = useState<ValidationTab>('candidate');
  const [index, setIndex] = useState(0);
  const [focus, setFocus] = useState<FocusResponse | null>(null);
  const [filtered, setFiltered] = useState<FilteredValidationWindow | null>(
    null,
  );
  const [reviewLabel, setReviewLabel] = useState('');
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    eogValidationApi
      .recording(sessionId)
      .then(async (recordingResult) => {
        if (controller.signal.aborted) return;
        if (!recordingResult.available) {
          setRecording(null);
          return;
        }
        const [candidateResult, controlResult, progressResult] =
          await Promise.all([
            eogValidationApi.samples(sessionId, 'candidate'),
            eogValidationApi.samples(sessionId, 'control'),
            eogValidationApi.progress(),
          ]);
        if (controller.signal.aborted) return;
        setRecording(recordingResult);
        setCandidates(candidateResult);
        setControls(controlResult);
        setProgress(progressResult);
      })
      .catch(() => {
        if (!controller.signal.aborted) setRecording(null);
      });
    return () => controller.abort();
  }, [sessionId]);

  const activeKind: ReviewKind = tab === 'control' ? 'control' : 'candidate';
  const samples = activeKind === 'candidate' ? candidates : controls;
  const sample = samples[index] ?? null;
  const labels = activeKind === 'candidate' ? candidateLabels : controlLabels;
  const primaryAgreement = useMemo(
    () =>
      recording?.agreement.filter((row) => Number(row.tolerance_s) === 0.5) ??
      [],
    [recording],
  );

  if (!recording) return null;

  const selectTab = (next: ValidationTab) => {
    setTab(next);
    setIndex(0);
    setFocus(null);
    setFiltered(null);
    setReviewLabel('');
    setNotes('');
  };

  const openFocus = async () => {
    if (!sample) return;
    const result = await eogValidationApi.focus(sample.review_id);
    setFocus(result);
    setReviewLabel(result.review?.review_label ?? '');
    setNotes(result.review?.notes ?? '');
    onFocus(
      result.focus_start_s,
      result.focus_end_s,
      result.candidate_timestamp,
    );
    const channel =
      sample.sample_kind === 'candidate'
        ? sample.source_channel
        : result.eog_signals[0]?.channel;
    if (channel) {
      setFiltered(
        await eogValidationApi.filteredWindow(
          sessionId,
          channel,
          result.focus_start_s,
          result.focus_end_s - result.focus_start_s,
        ),
      );
    }
  };

  const saveReview = async () => {
    if (!sample || !reviewLabel) return;
    await eogValidationApi.saveReview(sample.review_id, reviewLabel, notes);
    setProgress(await eogValidationApi.progress());
    setStatus('Review saved locally; detector output unchanged.');
    setFocus(await eogValidationApi.focus(sample.review_id));
  };

  return (
    <details
      className="panel overflow-hidden"
      data-testid="eog-validation-panel"
    >
      <summary className="cursor-pointer border-b border-line px-4 py-3">
        <span className="eyebrow text-accent">RESEARCH VALIDATION</span>
        <span className="ml-3 font-semibold text-primary">
          Eye Movement Validation
        </span>
        <span className="ml-3 font-mono text-[0.6875rem] text-secondary">
          {recording.validation_version} · contract{' '}
          {recording.contract_sha256.slice(0, 12)}…
        </span>
      </summary>
      <div className="p-4">
        <p className="text-xs text-secondary">
          Eye Movement Candidates are EOG-derived review targets, not REM,
          dream, direction, saccade ground truth, or clinical labels.
        </p>
        <div className="mt-3 flex flex-wrap gap-2" role="tablist">
          {[
            ['candidate', 'Candidate Review'],
            ['control', 'Non-candidate Review'],
            ['agreement', 'Channel Agreement'],
            ['stages', 'Stage Distribution'],
            ['progress', 'Review Progress'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              onClick={() => selectTab(value as ValidationTab)}
              className={`rounded-control border px-3 py-2 text-xs ${
                tab === value
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-line text-secondary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === 'candidate' || tab === 'control' ? (
          <div className="mt-4" aria-label={`${activeKind} review`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-mono text-xs text-secondary">
                {samples.length ? index + 1 : 0} / {samples.length} ·{' '}
                {sample?.review_id ?? 'No sampled window'}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  aria-label="Previous review sample"
                  disabled={index === 0}
                  onClick={() => setIndex((value) => Math.max(0, value - 1))}
                  className="rounded-control border border-line p-2 disabled:opacity-40"
                >
                  <ChevronLeft size={14} />
                </button>
                <button
                  type="button"
                  aria-label="Next review sample"
                  disabled={index + 1 >= samples.length}
                  onClick={() =>
                    setIndex((value) => Math.min(samples.length - 1, value + 1))
                  }
                  className="rounded-control border border-line p-2 disabled:opacity-40"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
            {sample ? (
              <>
                <div className="mt-3 grid gap-2 text-xs sm:grid-cols-4">
                  <Metric label="Dataset" value={sample.dataset_id} />
                  <Metric label="Recording" value={sample.recording_id} />
                  <Metric label="Channel" value={sample.source_channel} />
                  <Metric label="Stage" value={sample.normalized_stage} />
                  <Metric
                    label="Timestamp"
                    value={`${Number(sample.timestamp).toFixed(3)} s`}
                  />
                  <Metric
                    label="Confidence"
                    value={sample.confidence ?? 'control window'}
                  />
                  <Metric
                    label="Amplitude"
                    value={
                      sample.amplitude_uv
                        ? `${Number(sample.amplitude_uv).toFixed(2)} µV`
                        : 'n/a'
                    }
                  />
                  <Metric
                    label="Agreement stratum"
                    value={sample.agreement_class}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => void openFocus()}
                  className="mt-3 inline-flex items-center gap-2 rounded-control bg-accent px-3 py-2 text-xs font-semibold text-canvas"
                >
                  <LocateFixed size={14} /> Open focused ±5 s review
                </button>
              </>
            ) : null}

            {focus ? (
              <div className="mt-4 border-t border-line pt-4">
                <p className="text-xs text-secondary">
                  Native EOG (
                  {focus.eog_signals.map((signal) => signal.channel).join(', ')}
                  ) and EEG (
                  {focus.eeg_signals.map((signal) => signal.channel).join(', ')}
                  ) are loaded through the Viewer’s bounded 10 s window. The
                  trace below is the frozen detector’s derived filtered channel.
                </p>
                {filtered ? (
                  <div className="mt-3 rounded-control bg-[#111d2a] p-3">
                    <UPlotTimeSeries
                      timestamps={filtered.timestamps}
                      lines={[
                        {
                          label: `${filtered.channel} · filtered`,
                          values: filtered.samples,
                          stroke: '#9b8cf4',
                        },
                      ]}
                      unit={filtered.unit}
                      height={180}
                      maxPoints={2000}
                      testId="validation-filtered-eog"
                      cursorTimestamp={focus.candidate_timestamp}
                      xRange={[focus.focus_start_s, focus.focus_end_s]}
                    />
                  </div>
                ) : null}
                <div
                  className="mt-3 flex flex-wrap gap-2"
                  aria-label="Review labels"
                >
                  {labels.map((label) => (
                    <button
                      key={label}
                      type="button"
                      aria-pressed={reviewLabel === label}
                      onClick={() => setReviewLabel(label)}
                      className={`rounded-control border px-3 py-2 text-xs ${
                        reviewLabel === label
                          ? 'border-warning bg-warning/10 text-warning'
                          : 'border-line text-primary'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <label className="mt-3 block text-xs text-secondary">
                  Researcher notes
                  <textarea
                    aria-label="Researcher notes"
                    maxLength={500}
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    className="mt-1 block min-h-20 w-full rounded-control border border-line bg-canvas p-2 text-primary"
                  />
                </label>
                <button
                  type="button"
                  disabled={!reviewLabel}
                  onClick={() => void saveReview()}
                  className="mt-3 inline-flex items-center gap-2 rounded-control border border-accent px-3 py-2 text-xs text-accent disabled:opacity-40"
                >
                  <Save size={14} /> Save review
                </button>
                <p className="mt-2 text-xs text-secondary" role="status">
                  {status}
                </p>
              </div>
            ) : null}
          </div>
        ) : null}

        {tab === 'agreement' ? (
          <SimpleTable
            headings={[
              'Channels',
              'Events',
              'Matched ±0.5 s',
              'Channel-only',
              'Agreement',
            ]}
            rows={primaryAgreement.map((row) => [
              `${row.channel_a} / ${row.channel_b}`,
              `${row.channel_a_events} / ${row.channel_b_events}`,
              row.matched_events,
              `${row.channel_a_only} / ${row.channel_b_only}`,
              Number(row.matched_proportion).toFixed(3),
            ])}
          />
        ) : null}

        {tab === 'stages' ? (
          <SimpleTable
            headings={[
              'Channel',
              'Annotation',
              'Stage',
              'Minutes',
              'Candidates',
              'Events/min',
            ]}
            rows={recording.stage_distribution
              .filter((row) => row.annotation_source === 'primary')
              .map((row) => [
                row.source_channel,
                row.annotation_source,
                row.stage,
                Number(row.stage_minutes).toFixed(1),
                row.candidate_count,
                row.candidate_events_per_minute
                  ? Number(row.candidate_events_per_minute).toFixed(3)
                  : 'n/a',
              ])}
          />
        ) : null}

        {tab === 'progress' && progress ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <Metric
              label="Candidates reviewed"
              value={`${progress.candidate_reviewed} / ${progress.candidate_total}`}
            />
            <Metric
              label="Controls reviewed"
              value={`${progress.control_reviewed} / ${progress.control_total}`}
            />
            <Metric
              label="Likely Eye Movement"
              value={String(progress.label_counts['Likely Eye Movement'] ?? 0)}
            />
            <Metric
              label="Artifact"
              value={String(
                progress.label_counts['Artifact / Non-eye-movement'] ?? 0,
              )}
            />
            <Metric
              label="Uncertain"
              value={String(progress.label_counts.Uncertain ?? 0)}
            />
            {Object.entries(progress.datasets).map(([dataset, value]) => (
              <Metric
                key={dataset}
                label={dataset}
                value={`${value.reviewed} / ${value.total}`}
              />
            ))}
          </div>
        ) : null}
      </div>
    </details>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-control bg-elevated p-3 text-xs">
      <p className="text-secondary">{label}</p>
      <p className="mt-1 break-words font-mono text-primary">{value}</p>
    </div>
  );
}

function SimpleTable({
  headings,
  rows,
}: {
  headings: string[];
  rows: string[][];
}) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-secondary">
          <tr>
            {headings.map((heading) => (
              <th key={heading} className="p-2">
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-line">
              {row.map((value, cell) => (
                <td key={cell} className="p-2 font-mono text-primary">
                  {value}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
