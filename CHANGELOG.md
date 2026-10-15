# Changelog

## 0.2.4 — 2026-10-16

- Add Comfy Registry metadata, an explicit runtime-package exclusion list and a manually triggered publishing workflow.
- Declare the bundled face-refinement scene-detection and smoothing dependencies explicitly; align the detector minimum with the Star7 H3 backend.
- Standardize Director operational events in English, with project/shot IDs, stage names, elapsed time and base-cache save/restore records.
- Report the originating execution failure once, preserving its original exception and traceback instead of relabeling dependent decode/encode steps as additional failures.
- Preserve interruption handling, lazy cache reuse, Chinese interface labels and the author's example workflow.
- Exclude local projects, material files, models, caches, logs and developer tests from the Registry package.

## 0.2.3 — 2026-10-15

- Add an opt-in image-description injection switch for character, scene and prop cards; preserve text and the switch across projects and material/project packages.
- Keep explicit voice references unchanged except for media-label substitution. When a bound voice is omitted from the prompt, add its actual audio label after the character image label without guessing speaker IDs.
- Update exported material-outline Skills and examples with explicit voice definitions, audio retention markers and independent speaker numbering.
- Allow standalone HD/face processing to reuse the exact displayed base cache when only motion-guide drift settings changed. Successful postprocessing acknowledges that choice without rewriting original base provenance; recover older completed process records by exact output/task match.
- Clear stale parameter notices after a valid unchanged status response and provide a direct link from drift details to its existing settings. Keep experimental motion-guide drift control disabled by default.
- Add a no-LoRA refinement option on a cloned model; correctly report zero refinement and separate upscale/refine timing.
- Raise minimum typography to 17px, body text to 18px and headings to 20px; remove the header tagline and align material-description controls.
- Keep only learned model upscaling and migrate retired interpolation-test settings without changing refinement parameters. No new image-upscale model or external node plugin is installed.
- Correct current-shot export documentation. Keep the author-provided workflow byte-for-byte unchanged; exclude local projects, materials, models, logs, caches and generated media.
- GPU quality and runtime improvements are not claimed; high-resolution tiled refinement remains workload-dependent.


## 0.2.2 — 2026-10-15

- Add project-package import at the top of project management and export for each saved project, preserving that project's own workflow and materials.
- Add global custom prompt text with an enable checkbox; disabling retains text, omits it from generation and does not treat inactive text edits as shot changes.
- Preserve custom prompt text and its switch through project/workflow/package saves and imports; include enabled content in prompt previews and explicit parameter-change details.
- Unify typography: minimum text 15px, controls 15px, body 16px and section headings 18px; improve secondary-text contrast and control spacing.
- Keep the author's example workflow unchanged and exclude local projects, materials, caches, models and generated media.

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
