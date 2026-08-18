import type { WakeMusicGeneration } from '../types';

export type ProductAnalysisState =
  'NOT_AVAILABLE' | 'ANALYZING' | 'READY' | 'ERROR';
export type ProductAnalysisFeature = {
  feature: 'alpha' | 'eye_movement' | 'wake_music_profile' | 'k_complex';
  state: ProductAnalysisState;
  summary: string;
  cache_hit?: boolean;
  reuse_kind?: string;
  duration_ms?: number;
  profile?: WakeMusicGeneration['profile'];
  descriptor_metadata?: Record<string, unknown>;
  channels?: Array<{
    channel: string;
    candidate_count?: number;
    feature_windows?: number;
  }>;
};

export type ProductAnalysisStatus = {
  analysis_api_version: 'dreamcore.automatic_analysis.v1';
  session_id: string;
  poll_interval_ms?: number;
  features: {
    alpha: ProductAnalysisFeature;
    eye_movement: ProductAnalysisFeature;
    wake_music_profile: ProductAnalysisFeature;
    k_complex: ProductAnalysisFeature;
  };
};

export interface AutomaticAnalysisApi {
  ensure(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<ProductAnalysisStatus>;
}

export class HttpAutomaticAnalysisApi implements AutomaticAnalysisApi {
  constructor(private readonly baseUrl = '/api/analysis/v1') {}

  async ensure(sessionId: string, signal?: AbortSignal) {
    const response = await fetch(
      `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}`,
      { signal },
    );
    const payload = (await response.json()) as
      { data: ProductAnalysisStatus } | { error: { message: string } };
    if (!response.ok || 'error' in payload) {
      throw new Error(
        'error' in payload ? payload.error.message : response.statusText,
      );
    }
    return payload.data;
  }
}

export const automaticAnalysisApi = new HttpAutomaticAnalysisApi();
