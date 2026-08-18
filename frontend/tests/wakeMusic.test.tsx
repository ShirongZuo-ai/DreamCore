import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { WakeMusicPanel } from '../src/components/wakeMusic/WakeMusicPanel';
import type { WakeMusicApi } from '../src/services/wakeMusicApi';
import type { WakeMusicGeneration } from '../src/types';

function result(seed = 42): WakeMusicGeneration {
  return {
    generation_id: `wm-${seed}`,
    cache_key: `cache-${seed}`,
    session_id: 'sc4001-alpha-v1',
    profile: {
      profile_version: 'dreamcore.wake_music.profile.v1',
      session_id: 'sc4001-alpha-v1',
      source_window: {
        start_s: 51660,
        end_s: 52260,
        selection:
          'last_configured_interval_preceding_annotation_confirmed_wake_transition',
        transition_time_s: 52260,
        preceding_stage: 'N1',
        wake_stage: 'W',
      },
      physiology: {
        activity_level: 0.72,
        event_rate_level: 0.4,
        event_rate_per_min: 8.3,
        activity_trend: 0.03,
        amplitude_level: 0.55,
        feature_row_count: 600,
        source_channel: 'EOG horizontal',
        source_feature: 'eye_movement_activity_v1',
      },
      music: {
        register: 'high',
        density: 'moderately_active',
        brightness: 'gradually_brighter',
        expressive_strength: 'natural',
        energy: 'calm_to_moderately_awake',
        energy_curve: 'slightly_rising',
        style_family: 'neoclassical',
        style_label: 'Neo-Classical',
        tempo_character: 'slow_to_moderate',
      },
      constraints: {
        max_energy: 'moderate',
        max_percussiveness: 'low_to_moderate',
        allow_aggressive_styles: false,
        allow_vocals: false,
      },
      mapping_version: 'wake_music_mapping.v1',
      generation_seed: seed,
      variation_id: `neoclassical.v0${(seed % 4) + 1}`,
      style_selection: 'auto_exploratory',
      mapping_context: 'exploratory physiology-to-music mapping',
    },
    prompt_configuration: {
      prompt: 'instrumental fixture',
      prompt_hash: `hash-${seed}`,
      style_family: 'neoclassical',
      style_label: 'Neo-Classical',
      variation_id: `neoclassical.v0${(seed % 4) + 1}`,
      variation_description: 'fixture arrangement',
      generation_seed: seed,
    },
    provider: 'minimax',
    model: 'music-2.6-free',
    generated_at: '2026-08-13T00:00:00Z',
    master_audio: {
      path: '/local/wake_music.mp3',
      audio_url: `/api/wake-music/wm-${seed}/audio/master`,
      duration_s: 328.463673,
      file_size_bytes: 1024,
      sample_rate_hz: 44100,
      channels: 2,
      bitrate: 256000,
    },
    wake_version: {
      strategy: 'first_excerpt_v1',
      start_s: 0,
      duration_s: 60,
      encoded_duration_s: 60.029388,
      fade_out_s: 3,
      fade_out_start_s: 57,
      path: '/local/wake_music_60s.mp3',
      audio_url: `/api/wake-music/wm-${seed}/audio`,
      file_size_bytes: 1024,
      sample_rate_hz: 44100,
      channels: 2,
      bitrate: 256000,
    },
    audio_url: `/api/wake-music/wm-${seed}/audio`,
    trace_id: 'safe-trace',
    cached: false,
    external_generation_stochastic: true,
  };
}

function api(generate = vi.fn(async () => result())) {
  return {
    generate,
    newVariation: vi.fn(async () => result(43)),
  } as unknown as WakeMusicApi;
}

describe('Wake Music product panel', () => {
  it('selects style, shows loading, then renders profile and audio player', async () => {
    const user = userEvent.setup();
    let resolve!: (value: WakeMusicGeneration) => void;
    const generate = vi.fn(
      () => new Promise<WakeMusicGeneration>((done) => (resolve = done)),
    );
    const mock = api(generate);
    render(<WakeMusicPanel sessionId="sc4001-alpha-v1" api={mock} />);

    await user.selectOptions(
      screen.getByLabelText('Wake Music Style'),
      'neoclassical',
    );
    await user.click(
      screen.getByRole('button', { name: 'Generate Wake Music' }),
    );
    expect(screen.getByTestId('wake-music-panel')).toHaveAttribute(
      'data-generation-status',
      'generating',
    );
    expect(screen.getByText(/Generating and saving/)).toBeVisible();
    resolve(result());

    expect(
      await screen.findByLabelText('Generated Wake Music player'),
    ).toHaveAttribute('src', '/api/wake-music/wm-42/audio');
    expect(screen.getByText('Wake Version · 1:00')).toBeVisible();
    expect(
      screen.getByRole('button', { name: 'Wake Version · 60 s' }),
    ).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/0.72 → High register/)).toBeVisible();
    expect(screen.getByText(/8.30 \/ min → Moderately active/)).toBeVisible();
    expect(generate).toHaveBeenCalledWith(
      expect.objectContaining({
        style: 'neoclassical',
        session_id: 'sc4001-alpha-v1',
      }),
    );
  });

  it('defaults to the Wake Version and allows explicit Full Track playback', async () => {
    const user = userEvent.setup();
    render(<WakeMusicPanel sessionId="sc4001-alpha-v1" api={api()} />);
    await user.click(
      screen.getByRole('button', { name: 'Generate Wake Music' }),
    );
    const player = await screen.findByLabelText('Generated Wake Music player');
    expect(player).toHaveAttribute('src', '/api/wake-music/wm-42/audio');
    await user.click(screen.getByRole('button', { name: 'Full Track' }));
    expect(
      screen.getByLabelText('Generated Wake Music player'),
    ).toHaveAttribute('src', '/api/wake-music/wm-42/audio/master');
    expect(screen.getByText('Full Track · 5:28')).toBeVisible();
  });

  it('requests a backend-seeded new variation from the prior generation', async () => {
    const user = userEvent.setup();
    const mock = api();
    render(<WakeMusicPanel sessionId="sc4001-alpha-v1" api={mock} />);
    await user.click(
      screen.getByRole('button', { name: 'Generate Wake Music' }),
    );
    await screen.findByLabelText('Generated Wake Music player');
    await user.click(
      screen.getByRole('button', { name: 'Generate New Variation' }),
    );
    await waitFor(() =>
      expect(mock.newVariation).toHaveBeenCalledWith('wm-42', 'auto'),
    );
    expect(await screen.findByText(/seed 43/)).toBeVisible();
  });

  it('shows a clean provider error without rendering a player', async () => {
    const user = userEvent.setup();
    const mock = api(
      vi.fn(async () =>
        Promise.reject(new Error('Rate limited — please try again shortly')),
      ),
    );
    render(<WakeMusicPanel sessionId="sc4001-alpha-v1" api={mock} />);
    await user.click(
      screen.getByRole('button', { name: 'Generate Wake Music' }),
    );
    expect(
      await screen.findByText('Rate limited — please try again shortly'),
    ).toBeVisible();
    expect(
      screen.queryByLabelText('Generated Wake Music player'),
    ).not.toBeInTheDocument();
  });
});
