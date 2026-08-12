export function formatOptionalMetric(
  value: number | null,
  unit: string,
  fractionDigits = 0,
): string {
  if (value === null) return '—';
  return `${value.toFixed(fractionDigits)} ${unit}`;
}
