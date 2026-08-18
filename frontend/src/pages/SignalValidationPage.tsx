import { useEffect, useState } from 'react';

import { PanelHeader } from '../components/common/PanelHeader';
import {
  SignalValidationApi,
  type SignalValidationSummary,
} from '../services/signalValidationApi';

const api = new SignalValidationApi();

function percent(value: number | null | undefined) {
  return value == null ? 'NA' : `${(value * 100).toFixed(1)}%`;
}

function decimal(value: number | null | undefined, digits = 3) {
  return value == null ? 'NA' : value.toFixed(digits);
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="metric-label">{label}</p>
      <p className="mt-1 font-mono text-lg font-semibold text-primary">
        {value}
      </p>
    </div>
  );
}

function Pending() {
  return (
    <section className="panel p-5" role="status">
      <PanelHeader title="Signal Validation" eyebrow="Internal diagnostics" />
      <p className="mt-4 text-sm text-secondary">
        Validation results are pending. Run the explicit local Signal Validation
        V1 job; opening this page never starts a benchmark.
      </p>
    </section>
  );
}

export function SignalValidationPage() {
  const [summary, setSummary] = useState<SignalValidationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void api
      .getSummary(controller.signal)
      .then(setSummary)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            reason instanceof Error
              ? reason.message
              : 'Validation summary unavailable',
          );
        }
      });
    return () => controller.abort();
  }, []);

  if (!summary) {
    return (
      <div className="space-y-4" data-testid="signal-validation-page">
        <Pending />
        {error ? <p className="text-xs text-warning">{error}</p> : null}
      </div>
    );
  }

  const eye =
    summary.eye_movement.pooled_candidate_agreement_with_expert_rem_labels;
  const expert1 = summary.k_complex.experts.expert_1;
  const expert2 = summary.k_complex.experts.expert_2;
  const matrix = Object.entries(summary.cross_talk.contamination_matrix);

  return (
    <div className="min-w-0 space-y-5" data-testid="signal-validation-page">
      <div>
        <p className="eyebrow">Internal diagnostics · explicit offline job</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-primary">
          Signal Validation
        </h1>
        <p className="mt-1 text-sm text-secondary">
          Interpretable benchmark evidence for frozen production algorithms. Not
          a clinical score.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel p-5" aria-label="Alpha validation metrics">
          <PanelHeader
            title="Alpha"
            eyebrow={`${summary.alpha.case_count} synthetic cases`}
          />
          <div className="mt-5 grid grid-cols-2 gap-5">
            <Metric
              label="Frequency MAE"
              value={`${decimal(summary.alpha.frequency_error.mae)} Hz`}
            />
            <Metric
              label="Reliable peak detection"
              value={percent(
                summary.alpha.positive_reliable_peak_detection_rate,
              )}
            />
            <Metric
              label="False reliable peak"
              value={percent(summary.alpha.negative_false_reliable_peak_rate)}
            />
            <Metric
              label="Power recovery r"
              value={decimal(summary.alpha.absolute_power_pearson_r)}
            />
            <Metric
              label="Relative power stability SD"
              value={decimal(
                summary.alpha.stationary_stability.relative_power_sd.median,
              )}
            />
          </div>
        </section>

        <section
          className="panel p-5"
          aria-label="Eye Movement validation metrics"
        >
          <PanelHeader
            title="Eye Movement"
            eyebrow="DREAMS expert REM agreement"
          />
          <div className="mt-5 grid grid-cols-2 gap-5">
            <Metric
              label="Expert REM events"
              value={String(summary.eye_movement.expert_events_evaluable)}
            />
            <Metric
              label="DreamCore candidates"
              value={String(summary.eye_movement.dreamcore_candidate_count)}
            />
            <Metric label="Expert-event coverage" value={percent(eye.recall)} />
            <Metric
              label="Candidate agreement"
              value={percent(eye.precision)}
            />
            <Metric
              label="Timing MAE to interval midpoint"
              value={`${decimal(summary.eye_movement.timing_offset_from_expert_interval_midpoint_s.mae)} s`}
            />
            <Metric
              label="Human QC"
              value={
                summary.eye_movement.human_qc.review_count > 0
                  ? `${summary.eye_movement.human_qc.review_count} reviewed`
                  : summary.eye_movement.human_qc.status
              }
            />
          </div>
          <p className="mt-4 border-t border-line pt-4 text-xs text-secondary">
            General DreamCore candidates are not semantically identical to
            expert rapid-eye-movement labels.
          </p>
        </section>

        <section
          className="panel p-5"
          aria-label="K-Complex validation metrics"
        >
          <PanelHeader title="K-Complex" eyebrow="Independent DREAMS experts" />
          <div className="mt-5 grid grid-cols-2 gap-5 sm:grid-cols-3">
            <Metric
              label="Expert 1 precision"
              value={percent(expert1.precision)}
            />
            <Metric label="Expert 1 recall" value={percent(expert1.recall)} />
            <Metric label="Expert 1 F1" value={decimal(expert1.f1)} />
            <Metric
              label="Expert 2 precision"
              value={percent(expert2.precision)}
            />
            <Metric label="Expert 2 recall" value={percent(expert2.recall)} />
            <Metric label="Expert 2 F1" value={decimal(expert2.f1)} />
            <Metric
              label="Inter-expert F1"
              value={decimal(summary.k_complex.inter_expert_agreement.f1)}
            />
          </div>
          <p className="mt-4 border-t border-line pt-4 text-xs text-secondary">
            {summary.k_complex.trough_validation_status}
          </p>
        </section>

        <section
          className="panel overflow-hidden"
          aria-label="Cross-feature contamination matrix"
        >
          <div className="p-5">
            <PanelHeader
              title="Cross-talk"
              eyebrow={`${summary.cross_talk.case_count} deterministic stress cases`}
            />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[42rem] text-left text-xs">
              <thead className="bg-elevated text-secondary">
                <tr>
                  <th className="px-4 py-3">Injected case</th>
                  <th className="px-4 py-3">Reliable Alpha</th>
                  <th className="px-4 py-3">KC case detection</th>
                  <th className="px-4 py-3">EOG case detection</th>
                  <th className="px-4 py-3">False KC / h</th>
                  <th className="px-4 py-3">False EOG / h</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {matrix.map(([name, row]) => (
                  <tr key={name}>
                    <td className="px-4 py-3 font-mono text-primary">
                      {name.replaceAll('_', ' ')}
                    </td>
                    <td className="px-4 py-3 text-secondary">
                      {percent(row.mean_reliable_alpha_peak_rate)}
                    </td>
                    <td className="px-4 py-3 text-secondary">
                      {percent(row.k_complex_detected_case_rate)}
                    </td>
                    <td className="px-4 py-3 text-secondary">
                      {percent(row.eog_candidate_detected_case_rate)}
                    </td>
                    <td className="px-4 py-3 text-secondary">
                      {row.true_k_complex
                        ? 'NA'
                        : decimal(row.mean_false_k_complex_per_hour, 1)}
                    </td>
                    <td className="px-4 py-3 text-secondary">
                      {row.true_eog
                        ? 'NA'
                        : decimal(row.mean_false_eye_candidates_per_hour, 1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <p className="font-mono text-[0.625rem] text-secondary">
        Contract {summary.contract_sha256.slice(0, 16)}… ·{' '}
        {summary.validation_version}
      </p>
    </div>
  );
}
