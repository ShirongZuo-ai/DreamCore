import {
  ArrowLeft,
  Database,
  FileClock,
  Layers3,
  Radio,
  ShieldCheck,
} from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import { CapabilityStatus } from '../components/common/CapabilityStatus';
import { PanelHeader } from '../components/common/PanelHeader';
import { sessionCatalogService } from '../services/sessionCatalogService';
import type { CapabilityName } from '../types';

const capabilityLabels: Record<CapabilityName, string> = {
  eeg: 'EEG',
  sleep_stage_labels: 'Sleep-stage labels',
  sleep_stage_predictions: 'Sleep-stage predictions',
  slow_oscillation_detection: 'Slow oscillation detection',
  phase_estimation: 'Phase estimation',
  phase_precision: 'Phase precision',
  decision_simulation: 'Decision simulation',
  heart_rate: 'Heart rate',
  ppg: 'PPG',
  spo2: 'SpO₂',
  movement: 'Movement',
  snoring: 'Snoring',
  arousals: 'Arousals',
  artifacts: 'Artifacts',
  stimulation_events: 'Stimulation events',
  hardware_telemetry: 'Hardware telemetry',
  navigation_alignment: 'Navigation alignment',
};

function durationLabel(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours} h ${minutes.toString().padStart(2, '0')} min`;
}

export function SessionDetailsPage() {
  const { datasetId = '', sessionId = '' } = useParams();
  let manifest;
  try {
    manifest = sessionCatalogService.getSession(datasetId, sessionId);
  } catch {
    return (
      <div className="grid min-h-[60vh] place-items-center text-center">
        <div>
          <h1 className="text-xl font-semibold text-primary">
            Session package not found
          </h1>
          <Link to="/datasets" className="mt-4 inline-flex text-sm text-accent">
            Return to Dataset Library
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-5" data-testid="session-details-page">
      <div>
        <Link
          to="/datasets"
          className="inline-flex items-center gap-2 text-xs text-secondary hover:text-primary"
        >
          <ArrowLeft aria-hidden="true" size={14} /> Dataset Library
        </Link>
        <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <p className="eyebrow">Canonical session package</p>
              <span className="demo-chip">Test Fixture</span>
            </div>
            <h1 className="mt-1 font-mono text-2xl font-semibold text-primary">
              {manifest.session.session_id}
            </h1>
            <p className="mt-1 text-sm text-secondary">
              {manifest.dataset.display_name} · {manifest.session.subject_id}
            </p>
          </div>
          <span className="rounded-control border border-line bg-elevated px-3 py-2 font-mono text-xs text-secondary">
            {manifest.schema_version}
          </span>
        </div>
      </div>

      <section
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
        aria-label="Overview"
      >
        {[
          ['Dataset', manifest.dataset.id],
          ['Subject', manifest.session.subject_id],
          ['Duration', durationLabel(manifest.recording.duration_seconds)],
          ['Provenance', manifest.provenance.classification],
        ].map(([label, value]) => (
          <div className="panel p-4" key={label}>
            <p className="metric-label">{label}</p>
            <p className="mt-2 truncate font-mono text-sm font-semibold text-primary">
              {value}
            </p>
          </div>
        ))}
      </section>

      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <section className="panel p-4 sm:p-5">
          <PanelHeader
            title="Signals"
            eyebrow="Windowed metadata"
            action={
              <Radio aria-hidden="true" size={17} className="text-accent" />
            }
          />
          <div className="mt-4 divide-y divide-line">
            {manifest.signals.length ? (
              manifest.signals.map((signal) => (
                <div
                  className="grid grid-cols-[1fr_auto] gap-4 py-3"
                  key={signal.id}
                >
                  <div className="min-w-0">
                    <p className="font-mono text-sm font-semibold text-primary">
                      {signal.id}
                    </p>
                    <p className="mt-1 text-xs text-secondary">
                      {signal.modality} · {signal.channel_name} · {signal.unit}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-sm text-primary">
                      {signal.sampling_rate_hz} Hz
                    </p>
                    <p className="mt-1 text-[0.6875rem] text-secondary">
                      {signal.source}
                    </p>
                  </div>
                </div>
              ))
            ) : (
              <p className="py-5 text-sm text-secondary">
                No signal metadata in this package.
              </p>
            )}
          </div>
        </section>

        <section className="panel p-4 sm:p-5">
          <PanelHeader
            title="Capabilities"
            eyebrow="Explicit availability"
            action={
              <ShieldCheck
                aria-hidden="true"
                size={17}
                className="text-success"
              />
            }
          />
          <div className="mt-4 grid gap-x-6 sm:grid-cols-2">
            {(Object.keys(manifest.capabilities) as CapabilityName[]).map(
              (name) => (
                <div
                  className="flex items-center justify-between gap-3 border-t border-line py-2.5"
                  key={name}
                >
                  <span className="text-xs text-secondary">
                    {capabilityLabels[name]}
                  </span>
                  <CapabilityStatus capability={manifest.capabilities[name]} />
                </div>
              ),
            )}
          </div>
        </section>
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-3">
        {[
          {
            title: 'Annotations',
            eyebrow: 'Declared source content',
            items: manifest.annotations,
            icon: FileClock,
          },
          {
            title: 'Derived Results',
            eyebrow: 'Computed content',
            items: manifest.derived,
            icon: Layers3,
          },
        ].map(({ title, eyebrow, items, icon: Icon }) => (
          <section className="panel p-4 sm:p-5" key={title}>
            <PanelHeader
              title={title}
              eyebrow={eyebrow}
              action={
                <Icon aria-hidden="true" size={17} className="text-accent" />
              }
            />
            <div className="mt-4 divide-y divide-line">
              {Object.entries(items).map(([name, descriptor]) => (
                <div className="py-2.5" key={name}>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs text-primary">
                      {name.replaceAll('_', ' ')}
                    </span>
                    <span
                      className={
                        descriptor.available
                          ? 'text-xs text-success'
                          : 'text-xs text-secondary'
                      }
                    >
                      {descriptor.available ? 'Available' : 'Unavailable'}
                    </span>
                  </div>
                  {descriptor.reason ? (
                    <p className="mt-1 text-[0.6875rem] text-secondary">
                      {descriptor.reason}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        ))}

        <section className="panel p-4 sm:p-5">
          <PanelHeader
            title="Provenance"
            eyebrow="Traceability"
            action={
              <Database aria-hidden="true" size={17} className="text-accent" />
            }
          />
          <dl className="mt-4 divide-y divide-line">
            {[
              ['Classification', manifest.provenance.classification],
              ['Imported by', manifest.provenance.imported_by ?? 'Unknown'],
              [
                'Source URI',
                manifest.provenance.source_dataset_uri ?? 'Not applicable',
              ],
              ['Notes', manifest.provenance.notes ?? 'None'],
            ].map(([label, value]) => (
              <div className="py-2.5" key={label}>
                <dt className="text-[0.6875rem] text-secondary">{label}</dt>
                <dd className="mt-1 text-xs leading-5 text-primary">{value}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </div>
  );
}
