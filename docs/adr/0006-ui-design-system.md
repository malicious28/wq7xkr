# ADR 0006: UI design system: colour means data, glass and scroll share one frame loop

- Status: accepted
- Date: 2026-10-25

## Colour

- **Series colours are reserved for data entities and fixed across the app**: WINDFOR forecast = blue, actual outturn = orange, bias-adjusted = aqua, additive debias = yellow, persistence = violet. Controls and chrome use neutral ink, so a coloured mark always means a series.
- Both palettes (dark and light) were checked with a colour-vision-deficiency validator: lightness band, chroma floor, deutan/protan separation of at least 8 ΔE (OKLab), normal-vision floor, and contrast against each theme's chart surface. Light-mode aqua and yellow fall below 3:1 contrast, so those charts carry direct labels and a table view.
- Signed errors use a **diverging** scale (cool = forecast too low, warm = too high, neutral midpoint). Heatmap magnitudes use a one-hue **sequential** ramp. Status (pass, warning, fail) always comes with an icon and a text label.
- Metric lines (MAE, RMSE, bias) are not entities, so they use ink rather than series colours.

## Time

Every timestamp is UTC in the API and is rendered in **Europe/London explicitly**, never in the browser's zone. Charts run with `useUTC: true` on values pre-shifted to UK wall-clock time (`ukWallClockMs`). GMT/BST is derived from the actual offset, because Intl's short zone names vary by browser ("GMT" vs "GMT+0").

## Motion: Lenis + liquidGL

- **Lenis** (smooth scroll) and **liquidGL** (WebGL liquid glass) run on **one** `requestAnimationFrame` loop. `liquidGL.syncWith({ lenis })` drives `lenis.raf()`, so glass refraction and scroll position update in the same frame.
- liquidGL has no React bindings. `motion/glass.ts` wraps it in a handle-based API with lazy import (it lives in its own chunk), StrictMode-safe registration, and a CSS-frost fallback when WebGL is unavailable or `?glass=off` is set.
- **A stacking-context gotcha, found during visual QA**: outside a fixed or sticky ancestor, liquidGL draws on a canvas appended to `<body>`. Content nested inside the lens is trapped beneath that canvas. The fix:
  - the lens is an empty layer, and the content is its sibling one z-step above it (`GlassPanel`);
  - the content is marked `data-liquid-ignore`, so the lens doesn't refract its own text;
  - the shell creates no stacking context.
- Both libraries respect `prefers-reduced-motion`.

## Charts

- ECharts is tree-shaken, with the SVG renderer. Option builders are **pure functions** (data + tokens → option) and are unit-tested.
- Every chart has a written accessible name and a table view. ECharts' generated ARIA text, which dumps raw values, is disabled because it overwrote our labels.
- Tooltips are built as DOM nodes with `textContent`, never HTML strings.
- Filters live in the URL, so every view is a shareable link, and slider-driven queries are debounced.
