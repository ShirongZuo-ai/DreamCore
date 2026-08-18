import { Activity, Brain, Music2, Sparkles } from 'lucide-react';

import {
  type ProductAnalysisFeature,
  type ProductAnalysisStatus,
} from '../../services/automaticAnalysisApi';
import {
  kComplexApi as defaultKComplexApi,
  type KComplexApi,
  type KComplexEvent,
  type KComplexPayload,
} from '../../services/kComplexApi';
import { KComplexPanel } from './KComplexPanel';
import { useState } from 'react';

function FeatureRow({
  icon,
  label,
  feature,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  feature?: ProductAnalysisFeature;
  onClick?: () => void;
}) {
  const state = feature?.state ?? 'ANALYZING';
  const text = feature?.summary ?? 'Analyzing...';
  return (
    <button
      type="button"
      disabled={!onClick}
      onClick={onClick}
      className="flex min-h-14 w-full items-center justify-between gap-4 rounded-card border border-line bg-canvas/35 px-3 py-2 text-left disabled:cursor-default"
    >
      <div className="flex items-center gap-2 text-sm font-medium text-primary">
        <span className="text-accent" aria-hidden="true">
          {icon}
        </span>
        {label}
      </div>
      <span
        className={
          state === 'ERROR'
            ? 'text-xs text-danger'
            : state === 'READY'
              ? 'text-xs text-success'
              : 'text-xs text-secondary'
        }
      >
        {text}
      </span>
    </button>
  );
}

export function SleepInsightsPanel({
  status,
  sessionId,
  kComplex,
  selectedKComplex,
  currentTime = 0,
  kComplexApi = defaultKComplexApi,
  onSelectKComplex,
  onRefreshKComplex,
}: {
  status: ProductAnalysisStatus | null;
  sessionId?: string;
  kComplex?: KComplexPayload | null;
  selectedKComplex?: KComplexEvent | null;
  currentTime?: number;
  kComplexApi?: KComplexApi;
  onSelectKComplex?: (event: KComplexEvent) => void;
  onRefreshKComplex?: () => Promise<void>;
}) {
  const [kComplexOpen, setKComplexOpen] = useState(false);
  return (
    <section
      className="panel p-4"
      aria-label="Sleep Insights"
      data-testid="sleep-insights"
      aria-live="polite"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="eyebrow text-accent">SLEEP INSIGHTS</p>
          <h2 className="mt-1 font-semibold text-primary">
            Your recording analysis
          </h2>
        </div>
        <Sparkles className="text-accent" size={19} aria-hidden="true" />
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <FeatureRow
          icon={<Activity size={16} />}
          label="Eye Movement"
          feature={status?.features.eye_movement}
        />
        <FeatureRow
          icon={<Brain size={16} />}
          label="Alpha Activity"
          feature={status?.features.alpha}
        />
        <FeatureRow
          icon={<Sparkles size={16} />}
          label="K-Complex"
          feature={status?.features.k_complex}
          onClick={
            status?.features.k_complex.state === 'READY'
              ? () => setKComplexOpen((open) => !open)
              : undefined
          }
        />
        <FeatureRow
          icon={<Music2 size={16} />}
          label="Wake Music"
          feature={status?.features.wake_music_profile}
        />
      </div>
      {kComplexOpen &&
      sessionId &&
      kComplex &&
      onSelectKComplex &&
      onRefreshKComplex ? (
        <KComplexPanel
          sessionId={sessionId}
          payload={kComplex}
          selectedEvent={selectedKComplex ?? null}
          currentTime={currentTime}
          api={kComplexApi}
          onSelect={onSelectKComplex}
          onRefresh={onRefreshKComplex}
        />
      ) : null}
    </section>
  );
}
