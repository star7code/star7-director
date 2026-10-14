# Changelog

## 0.2.1 — 2026-10-15

- Fix film assembly when clips have different audio rates, channel counts or missing audio; preserve compatible video without re-generation.
- Preserve native model audio rate when encoding new clips.
- Show all segmented exports with a compact playlist and preview navigation.
- Save all exported clips or their ZIP package to a selected directory, with collision-safe names and cancellation handling.
- Use the modern Windows folder picker for local downloads; avoid Electron's stuck browser picker and repeated submissions.
- Export the current shot directly to the selected directory without an extra permanent output copy.
- Keep the author's example workflow unchanged; exclude all local projects, media and caches.

## 0.2.0 — 2026-10-14

- Author-provided Star7导演台.json replaces old unapproved examples; original layout and settings preserved.
- Exactly two public Director nodes; private bundled H3 implementation and native encoding, without VHS.
- Fix workflow tab removal, panel reattachment and delayed-state isolation; export history keeps the real canvas.
- Explicit shot-parameter comparison and revert detection; external model/LoRA changes do not dirty all shots.
- Right-click shot insertion, segmented export and separate timestamped export folders.
- Export-only format/FPS/quality/bitrate/audio settings; defaults preserve existing clips.
- Select project caches for manual deletion while retaining videos and materials.
- Detail preset uses eight steps; storyboard R and exported Skills use Motion Guide.
- Extended CPU, native video and isolated browser regressions.


## 0.1.0 — 2026-10-14

First public preview of Star7 Director for ComfyUI and MiniMax H3.

- Canvas director desk, material library and stable prompt references.
- Storyboard import/export, project packages and per-project local storage.
- Sequential background generation, selectable batches and queue inspection/cancellation.
- First-pass previews, HD refinement, face refinement and explicit displayed-result stages.
- Independent shots, continuity references and deferred previous-tail keyframes.
- Parameter-change details, reference-change notices and conservative result reuse.
- Reusable continuous preview, individual exports and merged-film export.
- Folded-star SVG branding and CPU regression tests. The old development workflow examples were withdrawn from main before v0.2.0.

Release source excludes all local projects, caches, logs, media, weights and generated outputs.
