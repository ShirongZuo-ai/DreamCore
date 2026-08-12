import { CircleHelp, CircleOff, Clock3 } from 'lucide-react';

import type { CapabilityDescriptor } from '../../types';

export function MissingDataState({
  label,
  capability,
  compact = false,
}: {
  label: string;
  capability: CapabilityDescriptor;
  compact?: boolean;
}) {
  const config =
    capability.status === 'PLANNED'
      ? { title: 'Planned', icon: Clock3, color: 'text-warning' }
      : capability.status === 'UNKNOWN'
        ? { title: 'Unknown', icon: CircleHelp, color: 'text-secondary' }
        : { title: 'Unavailable', icon: CircleOff, color: 'text-secondary' };
  const Icon = config.icon;

  if (compact) {
    return (
      <div className="min-w-0">
        <p
          className={`flex items-center gap-1.5 text-sm font-medium ${config.color}`}
        >
          <Icon aria-hidden="true" size={14} />
          {capability.status === 'UNAVAILABLE'
            ? 'Unavailable in this session'
            : config.title}
        </p>
        <p className="mt-1 truncate text-[0.6875rem] text-secondary">
          {capability.reason ?? `${label} is not available for this session`}
        </p>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 rounded-control border border-line bg-elevated p-3">
      <Icon
        aria-hidden="true"
        className={`mt-0.5 shrink-0 ${config.color}`}
        size={16}
      />
      <div className="min-w-0">
        <p className="text-sm font-medium text-primary">
          {label}: {config.title}
        </p>
        <p className="mt-1 text-xs leading-5 text-secondary">
          {capability.reason ??
            'This session package does not declare the data.'}
        </p>
      </div>
    </div>
  );
}
