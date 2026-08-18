import {
  ChevronLeft,
  ChevronRight,
  LocateFixed,
  ScanSearch,
} from 'lucide-react';
import { useMemo, useState } from 'react';

import type {
  KComplexApi,
  KComplexEvent,
  KComplexPayload,
  KComplexReview,
} from '../../services/kComplexApi';

function clock(seconds: number) {
  const milliseconds = Math.round(seconds * 1000);
  const hours = Math.floor(milliseconds / 3_600_000);
  const minutes = Math.floor((milliseconds % 3_600_000) / 60_000);
  const secs = Math.floor((milliseconds % 60_000) / 1000);
  const millis = milliseconds % 1000;
  return [hours, minutes, secs]
    .map((value) => String(value).padStart(2, '0'))
    .join(':')
    .concat(`.${String(millis).padStart(3, '0')}`);
}

export function KComplexPanel({
  sessionId,
  payload,
  selectedEvent,
  currentTime,
  api,
  onSelect,
  onRefresh,
}: {
  sessionId: string;
  payload: KComplexPayload;
  selectedEvent: KComplexEvent | null;
  currentTime: number;
  api: KComplexApi;
  onSelect: (event: KComplexEvent) => void;
  onRefresh: () => Promise<void>;
}) {
  const [notes, setNotes] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [advancedComparison, setAdvancedComparison] = useState(false);
  const [showRejected, setShowRejected] = useState(false);
  const events = useMemo(
    () =>
      showRejected
        ? payload.events
        : payload.events.filter(
            (event) => event.verification_status === 'accepted',
          ),
    [payload.events, showRejected],
  );
  const selectedIndex = selectedEvent
    ? events.findIndex((event) => event.event_id === selectedEvent.event_id)
    : -1;
  const byBout = useMemo(
    () =>
      payload.bouts.map((bout) => ({
        bout,
        events: events.filter((event) => event.n2_bout_id === bout.bout_id),
      })),
    [events, payload.bouts],
  );
  const selectedReview = selectedEvent
    ? payload.reviews.find(
        (review) => review.event_id === selectedEvent.event_id,
      )
    : undefined;

  const saveReview = async (label: KComplexReview['review_label']) => {
    if (!selectedEvent) return;
    setSaving(true);
    setMessage(null);
    try {
      await api.review(sessionId, selectedEvent.event_id, label, notes);
      await onRefresh();
      setMessage(`${label} saved locally.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Review failed');
    } finally {
      setSaving(false);
    }
  };

  const markManual = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.markManual(sessionId, currentTime, notes);
      await onRefresh();
      setMessage(`Manual K-complex trough saved at ${clock(currentTime)}.`);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : 'Manual mark must be inside N2',
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="mt-3 border-t border-line pt-3"
      data-testid="k-complex-panel"
    >
      <div className="grid gap-2 text-xs sm:grid-cols-4">
        <Metric
          label="K-Complex"
          value={`${payload.verified_count} verified`}
        />
        <Metric label="V0 candidates" value={String(payload.candidate_count)} />
        <Metric
          label="Rejected by verifier"
          value={String(payload.rejected_count)}
        />
        <Metric
          label="N2 bouts with events"
          value={String(payload.analysis.n2_bouts_with_events)}
        />
        <Metric
          label="Human review"
          value={`Reviewed ${payload.review_progress.reviewed} / ${payload.review_progress.total}`}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 border-y border-line py-2 text-xs">
        <label className="inline-flex items-center gap-2 text-primary">
          <input
            type="checkbox"
            checked={showRejected}
            onChange={(event) => setShowRejected(event.target.checked)}
            className="accent-accent"
          />
          Show rejected V0 candidates
        </label>
        <label className="inline-flex items-center gap-2 text-primary">
          <input
            type="checkbox"
            checked={advancedComparison}
            onChange={(event) => setAdvancedComparison(event.target.checked)}
            className="accent-accent"
          />
          <ScanSearch size={14} /> CBraMod comparison
        </label>
        {advancedComparison ? (
          <>
            <span className="font-mono text-secondary">
              {payload.analysis.cbramod?.status ?? 'not_computed'}
            </span>
          </>
        ) : null}
      </div>

      <div className="mt-3 max-h-52 space-y-2 overflow-y-auto pr-1">
        {byBout.map(({ bout, events: boutEvents }) => (
          <div
            key={bout.bout_id}
            className="rounded-control border border-line bg-canvas/40 p-2"
          >
            <p className="font-semibold text-primary">
              N2 Bout {Number(bout.bout_id.split('-').at(-1))}
            </p>
            {boutEvents.length ? (
              <div className="mt-1 grid gap-1 sm:grid-cols-2">
                {boutEvents.slice(0, 2).map((event) => (
                  <button
                    type="button"
                    key={event.event_id}
                    onClick={() => onSelect(event)}
                    className="rounded-control border border-accent/30 px-2 py-1.5 text-left text-accent"
                  >
                    <strong>
                      {event.ordinal_in_n2_bout === 1
                        ? 'First K-Complex'
                        : event.ordinal_in_n2_bout === 2
                          ? 'Second K-Complex'
                          : `K-Complex candidate ${event.ordinal_in_n2_bout}`}
                    </strong>
                    <span className="block font-mono text-primary">
                      {clock(event.negative_trough_s)}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-secondary">
                No K-complex detected in this N2 bout.
              </p>
            )}
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={selectedIndex <= 0}
          onClick={() => onSelect(events[selectedIndex - 1])}
          className="inline-flex min-h-9 items-center gap-1 rounded-control border border-line px-2 text-xs text-primary disabled:opacity-40"
        >
          <ChevronLeft size={13} /> Previous KC
        </button>
        <button
          type="button"
          disabled={selectedIndex < 0 || selectedIndex >= events.length - 1}
          onClick={() => onSelect(events[selectedIndex + 1])}
          className="inline-flex min-h-9 items-center gap-1 rounded-control border border-line px-2 text-xs text-primary disabled:opacity-40"
        >
          Next KC <ChevronRight size={13} />
        </button>
        {selectedEvent ? (
          <button
            type="button"
            onClick={() => onSelect(selectedEvent)}
            className="inline-flex min-h-9 items-center gap-1 rounded-control bg-accent px-2 text-xs font-semibold text-canvas"
          >
            <LocateFixed size={13} /> Jump to event
          </button>
        ) : null}
      </div>

      {selectedEvent ? (
        <div
          className="mt-3 rounded-control border border-accent/40 bg-accent/5 p-3 text-xs"
          aria-label="Focused K-Complex event"
        >
          <div className="flex flex-wrap justify-between gap-2">
            <strong className="text-primary">
              {selectedEvent.n2_bout_id} · KC {selectedEvent.ordinal_in_n2_bout}
            </strong>
            <span className="font-mono text-accent">
              trough {clock(selectedEvent.negative_trough_s)}
            </span>
          </div>
          <p className="mt-1 text-secondary">
            {selectedEvent.channel} · {selectedEvent.stage} · bounds{' '}
            {selectedEvent.onset_s.toFixed(3)}–{selectedEvent.end_s.toFixed(3)}{' '}
            s · trough {selectedEvent.negative_trough_amplitude.toFixed(1)}{' '}
            {selectedEvent.amplitude_unit} · score{' '}
            {selectedEvent.score.toFixed(2)} ({selectedEvent.confidence})
          </p>
          <p className="mt-1 font-medium text-primary">
            {selectedEvent.verification_status === 'accepted'
              ? 'Verified'
              : 'Rejected'}{' '}
            by morphology verifier · probability{' '}
            {selectedEvent.verification_probability.toFixed(3)}
          </p>
          {advancedComparison ? (
            <div className="mt-2 grid gap-1 border-t border-line pt-2 sm:grid-cols-3">
              <Metric label="Candidate detector" value="K-Complex V0" />
              <Metric label="Verifier" value="Morphology B1" />
              <Metric
                label="B1 probability"
                value={selectedEvent.verification_probability.toFixed(3)}
              />
              <Metric
                label="Original trough"
                value={clock(selectedEvent.trough_s)}
              />
              <Metric
                label="Original morphology score"
                value={selectedEvent.original_morphology_score.toFixed(3)}
              />
              <Metric
                label="CBraMod verification"
                value={
                  selectedEvent.cbramod_probability === undefined
                    ? 'Not computed'
                    : `${selectedEvent.cbramod_probability.toFixed(3)} · ${selectedEvent.cbramod_status ?? 'uncertain'}`
                }
              />
            </div>
          ) : null}
          <p className="mt-1 text-secondary">
            Positive peak:{' '}
            {selectedEvent.positive_peak_s === null
              ? 'not confidently identified'
              : clock(selectedEvent.positive_peak_s)}
          </p>
          <p className="mt-1 text-warning">
            Retrospective complete-waveform detection · no causal lead-time
            claim
          </p>
          <textarea
            aria-label="K-Complex review notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Optional notes"
            className="mt-2 min-h-16 w-full rounded-control border border-line bg-canvas p-2 text-primary"
          />
          <div className="mt-2 flex flex-wrap gap-2">
            {(['Looks right', 'Wrong', 'Uncertain'] as const).map((label) => (
              <button
                type="button"
                key={label}
                disabled={saving}
                onClick={() => void saveReview(label)}
                className={`rounded-control border px-2 py-1.5 ${selectedReview?.review_label === label ? 'border-success text-success' : 'border-line text-primary'}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
        <button
          type="button"
          disabled={saving}
          onClick={() => void markManual()}
          className="rounded-control border border-warning/60 px-2 py-1.5 text-xs text-warning"
        >
          Mark K-Complex manually
        </button>
        <span className="text-xs text-secondary">
          Saves the current cursor as a separate manual N2 trough candidate.
        </span>
      </div>
      {message ? (
        <p className="mt-2 text-xs text-secondary">{message}</p>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-control border border-line bg-canvas/40 p-2">
      <p className="text-secondary">{label}</p>
      <p className="mt-0.5 font-mono font-semibold text-primary">{value}</p>
    </div>
  );
}
