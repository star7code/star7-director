# Storyboard exchange format

Required: `duration` (seconds, 0.1–60) and `prompt`. Optional: `name`. Preferred document:

```json
{"shots":[{"duration":5,"prompt":"A cinematic shot using @{actual_material_id}."},{"duration":3.5,"prompt":"A slow camera move through the same setting."}]}
```

The outline supplies real IDs; never use the placeholder above literally. The importer canonicalizes valid names/aliases into stable IDs, expands text materials when compiling, checks voice bindings/media limits/cycles, and rejects unknown references and manual model tokens. Fresh IDs are allocated beyond existing shot IDs, including replacement imports, so prior video caches cannot appear on new shots. Preview is non-mutating; commit is all-or-nothing and undoable. Markdown JSON fences, bare arrays, Chinese key aliases and numeric duration strings are supported; conversions are shown as warnings. Malformed, duplicate-key, ambiguous or truncated JSON is rejected.

Writing instructions in the outline are English and follow the metadata/scope/workflow/output/verification structure of an agent skill. This is a portable writing guide inside the exported outline, not an installed personal Codex skill. No file paths, weights, caches or secrets are exported.

Reference design sources:
- https://developers.openai.com/plugins/concepts/skills
- https://developers.openai.com/api/docs/guides/structured-outputs

No model API is needed for recognition; it is a deterministic parser and uses the same prompt compiler as actual generation.

## H3 structure and readable references
The outline now includes the official MiniMax three-field text/keyframe format and six-field full-reference format, subject definitions, stable speaker IDs, <d>[Language] exact dialogue</d>, sound/music distinctions and correct N/A usage. English instructions permit Chinese prose while preserving protocol labels. Primary material references use readable names, such as @{小可}; stable_reference remains available. The importer canonicalizes recognized names to internal IDs. Dialogue/lyrics inside <d> are literal, so emails and @ names spoken aloud are not treated as assets.

The per-shot 强调无字幕 checkbox appends `Screen: no subtitles, no on-screen text, no watermark.` exactly once at the end of the compiled generation prompt. It is not written into the authored prompt or imposed by the writing skill. The adjacent apply-all action includes that checkbox. This is a text preference, not a guarantee that the model never renders text.

Official H3 sources:
- https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills/h3-prompt-writing
- https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md
- https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md
