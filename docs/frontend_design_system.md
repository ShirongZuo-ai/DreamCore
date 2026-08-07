# Frontend Design System

## Direction

The interface should feel quiet, precise, and suitable for algorithm research.
It uses a dark blue-gray canvas rather than black, restrained cyan emphasis,
thin borders, consistent spacing, and little elevation. It intentionally avoids
neon glow, decorative telemetry, circular gauges, large gradients, 3D imagery,
particles, and continuously animated values.

## Tokens

The source of truth is `frontend/src/styles/tokens.css`; Tailwind aliases in
`tailwind.config.ts` reference these variables.

| Token | Default | Use |
|---|---:|---|
| `background` | `#0f1824` | Page canvas |
| `surface` | `#162230` | Primary panels |
| `elevated surface` | `#1b2a3a` | Controls and differentiated rows |
| `border` | `#2a3a4b` | Fine structural separators |
| `primary text` | `#eef5f7` | Main reading hierarchy |
| `secondary text` | `#91a4b7` | Labels, metadata, explanations |
| `accent` | `#3db5d8` | Navigation, EEG, selected/observing state |
| `stimulation` | `#9b8cf4` | Stimulation events only |
| `warning` | `#e1aa5a` | Attention and incomplete connection |
| `danger` | `#ef6574` | Stop and severe abnormal status only |
| `success` | `#59c59b` | Ready, complete, safe-disabled state |

## Spacing, radius, and depth

Spacing follows an 8 px base: 8, 16, 24, 32, 40, and 48 px. Controls use an
8 px radius; panels use 12 px. Panels use a thin border and one low-opacity
shadow. Do not nest a panel-style card inside another panel; internal grouping
uses dividers, background shifts, or plain spacing.

## Typography

The default stack is Inter with system fallbacks. IDs, timestamps, measurements,
and axis labels use the configured monospace stack. Labels remain readable at
11–12 px; primary values use 14–24 px according to hierarchy. Uppercase eyebrow
labels use increased tracking and are not used for body copy.

## Semantic states

- Normal/ready: success green.
- Observing/selected/informational: cyan accent.
- Attention/offline/partial: warning amber.
- Dangerous/stopped/critical: danger red.
- Stimulation event: purple, never reused as general decoration.
- Unknown/unavailable: secondary gray, never green.

Status never relies on color alone; text labels and icons accompany it.

## Motion and interaction

Transitions last 180–220 ms and are limited to color, border, background, and
opacity changes. No pulsing, flashing, waveform scrolling, or number animation
is permitted. `prefers-reduced-motion` reduces transitions and animations to
effectively zero. Keyboard focus uses a visible cyan outline.

## Responsive rules

- 1440 px: EEG and monitoring sidebar are side-by-side.
- 1280 px and below: EEG receives full width; decision, physiology, and safety
  panels form a secondary grid below it.
- Mobile: the header is compact, navigation becomes a fixed bottom bar, status
  grids use two columns, and all primary actions remain at least 44 px tall.
- Grids and flex children use `min-width: 0`; only purpose-built tables may use
  an internal horizontal scroller. The page itself must never scroll sideways.

## Content rules

Every mock measurement must disclose `Demo` or `Simulated` near the value or
module. Do not frame sleep stage proportions, SWS, or slow-wave activity as a
health score. Subject View must not expose experimental condition, stimulation
count, target, phase, raw EEG, or diagnostic interpretation.
