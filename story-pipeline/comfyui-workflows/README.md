# ComfyUI workflows

Workflows in **API format** (ComfyUI → enable dev mode → "Save (API Format)").
The backend fills these tokens before queueing a prompt:

| Token | Type | Filled with |
|---|---|---|
| `{{prompt}}` | string | style + scene/character prompt |
| `{{negative_prompt}}` | string | `models.image.negative_prompt` |
| `{{seed}}` | int | per-scene / per-character seed (stored for reproducibility) |
| `{{width}}`, `{{height}}` | int | `models.image.width/height` |
| `{{reference_image}}` | string | uploaded character reference sheet (optional) |

`*_v1.json` are a plain SDXL text-to-image graph so you can verify the
integration end to end. For real character consistency, build a `scene_v2.json`
that feeds `{{reference_image}}` through an IP-Adapter / reference-conditioning
node, then point `models.image.workflows.scene` at it. Version workflows by
filename: never edit a workflow that produced published videos.

Change `ckpt_name` to the checkpoint you actually have installed.

## Image-to-video: Wan 2.2 14B (hybrid_animation projects)

`image_to_video_wan22_14b.json` drives the **animate** stage. Recommended for a 24-48 GB GPU:
**Wan 2.2 14B image-to-video**, Apache 2.0 (fine for monetised channels), fp8 weights (~20 GB VRAM).
On a 48 GB card you can run 1280x720 / 81 frames (~5 s at 16 fps) without offloading.

Model files (ComfyUI's repackaged versions):

| Folder (`ComfyUI/models/...`) | File |
|---|---|
| `diffusion_models/` | `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` |
| `diffusion_models/` | `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` |
| `text_encoders/` | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` |
| `vae/` | `wan_2.1_vae.safetensors` |

Tokens the adapter fills: `{{image}}` (start frame, uploaded), `{{prompt}}`, `{{negative_prompt}}`,
`{{seed}}`, `{{width}}`, `{{height}}`, `{{frames}}` (use 4n+1), `{{fps}}`. The graph must end in a node that
saves an `.mp4`/`.webm` (core `SaveVideo`, or `VHS_VideoCombine`).

**This JSON was written from ComfyUI's native Wan nodes and has not been run.** The safest route:
open ComfyUI → Workflow → Browse Templates → Video → *Wan2.2 14B Image to Video*, check it renders,
then *Export (API)*, replace the image filename, prompt text, seed, width/height, length and fps
with the tokens above, and save it over this file (or under a new name + `models.video.workflow`).

Tips for a 48 GB card:
- Set `models.llm.keep_alive: "0"` so Ollama releases VRAM between calls; the animate stage also calls
  ComfyUI's `/free` when it finishes (`free_vram_after_stage`).
- Draft at 832x480 (about 4x faster), then switch to 1280x720 for the final version. The scene fingerprints
  include the resolution, so changing it re-animates.
- Clip time is minutes per scene at 720p; `max_animated_scenes` (default 3) keeps a video's GPU budget bounded.
