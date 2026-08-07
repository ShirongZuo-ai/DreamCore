export function ReviewMetric({
  label,
  value,
  helper,
}: {
  label: string;
  value: string;
  helper: string;
}) {
  return (
    <div className="panel min-w-0 p-4">
      <p className="metric-label">{label}</p>
      <p className="mt-2 font-mono text-xl font-semibold tracking-tight text-primary sm:text-2xl">
        {value}
      </p>
      <p className="mt-2 text-[0.6875rem] text-secondary">{helper} · Demo</p>
    </div>
  );
}
