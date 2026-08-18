import type { WakeMusicGeneration, WakeMusicStyle } from '../types';

type WakeMusicEnvelope<T> = { wake_music_api_version: 'v1'; data: T };
type WakeMusicFailure = {
  wake_music_api_version: 'v1';
  error: { code: string; message: string; details: Record<string, unknown> };
};

export type GenerateWakeMusicRequest = {
  session_id: string;
  style: WakeMusicStyle;
  generation_seed?: number;
  window_start_s?: number;
  window_end_s?: number;
};

export class WakeMusicApi {
  constructor(private readonly baseUrl = '/api/wake-music') {}

  private async request(
    body:
      | GenerateWakeMusicRequest
      | { new_variation_of: string; style: WakeMusicStyle },
  ): Promise<WakeMusicGeneration> {
    const response = await fetch(`${this.baseUrl}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const payload = (await response.json()) as
      WakeMusicEnvelope<WakeMusicGeneration> | WakeMusicFailure;
    if (!response.ok || 'error' in payload) {
      const code = 'error' in payload ? payload.error.code : 'request_failed';
      const message =
        'error' in payload ? payload.error.message : response.statusText;
      throw new WakeMusicApiError(code, message);
    }
    return payload.data;
  }

  generate(request: GenerateWakeMusicRequest) {
    return this.request(request);
  }

  newVariation(generationId: string, style: WakeMusicStyle) {
    return this.request({ new_variation_of: generationId, style });
  }

  async latest(sessionId: string): Promise<WakeMusicGeneration | null> {
    const response = await fetch(
      `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}/latest`,
    );
    const payload = (await response.json()) as
      WakeMusicEnvelope<WakeMusicGeneration | null> | WakeMusicFailure;
    if (!response.ok || 'error' in payload) return null;
    return payload.data;
  }
}

export class WakeMusicApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export const wakeMusicApi = new WakeMusicApi();
