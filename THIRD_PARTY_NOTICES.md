# Third-party code

The Star7 implementation is distributed under the root MIT LICENSE.

`vendor/aimixer/h3_motion_context.py`, `h3_latent_continue.py`, and their native compatibility adaptation derive from AIMixer/ComfyUI_MiniMaxH3_Director. These files retain their original copyright notices and Apache-2.0 license. See `vendor/aimixer/LICENSE` and `vendor/aimixer/NOTICE.md`.

`vendor/h3` contains the private Star7 H3 conditioning, refinement, preview and decode implementation. It is derived from the Star7 MIT-licensed backend; its LICENSE is included. `vendor/h3/vendor/h3facerefine` retains Carasibana's MIT license and copyright. These modules do not register additional ComfyUI nodes.

Model weights are not included. Their respective licenses continue to apply. Python dependencies such as PyAV, Ultralytics and imageio-ffmpeg retain their own licenses; they are declared in requirements.txt rather than copied as node plugins.
