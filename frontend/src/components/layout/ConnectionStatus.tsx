import { WifiOff } from 'lucide-react';

export function ConnectionStatus() {
  return (
    <span
      aria-label="Device Offline"
      className="inline-flex shrink-0 items-center gap-1.5 text-xs font-medium text-secondary"
    >
      <WifiOff aria-hidden="true" size={14} />
      <span className="hidden md:inline">Device Offline</span>
      <span className="md:hidden">Offline</span>
    </span>
  );
}
