import { OctagonAlert, RotateCcw } from 'lucide-react';

export function EmergencyStopButton({
  isStopped,
  onActivate,
  onReset,
}: {
  isStopped: boolean;
  onActivate: () => void;
  onReset: () => void;
}) {
  if (isStopped) {
    return (
      <button
        type="button"
        onClick={onReset}
        className="flex min-h-12 w-full items-center justify-center gap-2 rounded-control border border-danger/50 bg-danger/15 px-4 text-sm font-semibold text-danger sm:w-auto"
        aria-label="Reset local demo emergency stop"
      >
        <RotateCcw aria-hidden="true" size={17} />
        Demo Stop Active · Reset
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onActivate}
      className="flex min-h-12 w-full items-center justify-center gap-2 rounded-control border border-danger bg-danger/10 px-4 text-sm font-semibold text-danger hover:bg-danger/20 sm:w-auto"
      aria-label="Emergency Stop — local demo only"
    >
      <OctagonAlert aria-hidden="true" size={18} />
      Emergency Stop
    </button>
  );
}
