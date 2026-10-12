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
