---
name: SOLAR-EDU AI
description: Restrained, Vercel-inspired product UI. Ink on near-white, hairline structure, fixed semantic data colors, one brand green taken from the logo leaf.
colors:
  ink: "#171717"        # dark: #ededed
  body: "#4d4d4d"       # dark: #a3a3a3
  mute: "#6b6b6b"       # dark: #8f8f8f  (AA on canvas)
  line: "#ebebeb"       # dark: #262626
  canvas: "#ffffff"     # dark: #0a0a0a
  canvas-soft: "#fafafa" # dark: #111111
  pred: "#0070f3"       # dark: #5aa9ff  prediction lines/bands, focus ring
  pv: "#f5a623"         # solar production area
  pv-ink: "#8a5a00"     # dark: #f5a623  text on/near pv
  good: "#0b7a5b"       # dark: #3ecf9e  done, savings
  crit: "#c4160a"       # dark: #ff6b60  anomalies ONLY
  brand: "#0f7a5f"      # logo leaf green, used for logo context and active nav marker
typography:
  family: "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
  mono: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
  numbers: "font-variant-numeric: tabular-nums"
  scale: "12 / 13 / 14 / 16 / 20 / 24 / 32 (fixed rem, ratio ~1.2)"
  weights: "400 body, 500 buttons/labels, 600 headings and figures"
rounded: { sm: 6px, md: 8px, lg: 12px, pill: 999px }
spacing: { 1: 4px, 2: 8px, 3: 12px, 4: 16px, 5: 24px, 6: 32px, 7: 48px }
---

# SOLAR-EDU AI design system

## Theme

Scene: a building manager in a sunlit facilities office in Bengkulu checks the screen between rounds, often on a phone. Light theme by default, dark theme follows `prefers-color-scheme` and a manual toggle. Restrained color strategy: neutrals carry the surface, color is reserved for data meaning.

## Color rules

- Blue (`pred`) only for forecasts and their 10–90 % band, plus the focus ring.
- Amber (`pv`) only for solar production.
- Red (`crit`) only for anomalies and destructive confirmation. Always paired with a text label.
- Green (`good`) for completed states and measured savings.
- Primary buttons are ink-filled; secondary buttons are canvas with a hairline.

## Components

- App shell: left nav (desktop) / bottom-sheet menu (mobile), 56 px top bar with building name, data-simulation badge, notification bell, user menu.
- Panels: canvas surface, 1 px hairline, `rounded.lg`, no heavy shadow. Never nested.
- Status chips: pill, neutral tint + text; state color only as a small dot.
- Tables: caption-mono headers, tabular numbers right-aligned.
- Charts: SVG, role="img" with aria-label, focusable, arrow keys move a crosshair readout.
- Toasts: bottom-right, `aria-live="polite"`.

## Motion

150–200 ms ease-out-quart on color, opacity, transform. No page-load choreography. All motion disabled under `prefers-reduced-motion`.
