import { useState } from 'react';

export function useLocalEmergencyStop() {
  const [isStopped, setIsStopped] = useState(false);

  return {
    isStopped,
    activate: () => setIsStopped(true),
    resetDemo: () => setIsStopped(false),
  };
}
