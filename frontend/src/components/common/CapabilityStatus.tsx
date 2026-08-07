import { Circle, CircleCheck, CircleEllipsis, CircleOff } from 'lucide-react';

import type { CapabilityDescriptor, CapabilityStatus } from '../../types';

const presentation: Record<
  CapabilityStatus,
  { label: string; className: string; icon: typeof Circle }
> = {
  AVAILABLE: {
    label: 'Available',
    className: 'text-success',
    icon: CircleCheck,
  },
  UNAVAILABLE: {
    label: 'Unavailable',
    className: 'text-secondary',
    icon: CircleOff,
  },
  PLANNED: {
    label: 'Planned',
    className: 'text-warning',
    icon: CircleEllipsis,
  },
  UNKNOWN: {
    label: 'Unknown',
    className: 'text-secondary',
    icon: Circle,
  },
};

export function CapabilityStatus({
  capability,
  compact = false,
}: {
  capability: CapabilityDescriptor;
  compact?: boolean;
}) {
  const item = presentation[capability.status];
  const Icon = item.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-medium ${item.className}`}
      title={capability.reason}
    >
      <Icon aria-hidden="true" size={compact ? 12 : 14} />
      {compact ? <span className="sr-only">{item.label}</span> : item.label}
    </span>
  );
}
