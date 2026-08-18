import { useEffect, useState } from 'react';

import {
  automaticAnalysisApi,
  type AutomaticAnalysisApi,
  type ProductAnalysisStatus,
} from '../services/automaticAnalysisApi';

export function useAutomaticAnalysis({
  sessionId,
  enabled,
  api = automaticAnalysisApi,
}: {
  sessionId: string;
  enabled: boolean;
  api?: AutomaticAnalysisApi;
}) {
  const [status, setStatus] = useState<ProductAnalysisStatus | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const next = await api.ensure(sessionId, controller.signal);
        if (!active) return;
        setStatus(next);
        if (
          Object.values(next.features).some(
            (feature) => feature.state === 'ANALYZING',
          ) &&
          next.poll_interval_ms !== undefined
        ) {
          timer = setTimeout(() => void poll(), next.poll_interval_ms);
        }
      } catch (error) {
        if (
          active &&
          !(error instanceof DOMException && error.name === 'AbortError')
        ) {
          setStatus((current) => ({
            analysis_api_version: 'dreamcore.automatic_analysis.v1',
            session_id: sessionId,
            poll_interval_ms: current?.poll_interval_ms,
            features: {
              eye_movement: {
                feature: 'eye_movement',
                state: 'ERROR',
                summary: 'Error',
              },
              alpha: {
                feature: 'alpha',
                state: 'ERROR',
                summary: 'Error',
              },
              wake_music_profile: {
                feature: 'wake_music_profile',
                state: 'ERROR',
                summary: 'Error',
              },
              k_complex: {
                feature: 'k_complex',
                state: 'ERROR',
                summary: 'Error',
              },
            },
          }));
        }
      }
    };
    void poll();
    return () => {
      active = false;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [api, enabled, sessionId]);
  return status;
}
