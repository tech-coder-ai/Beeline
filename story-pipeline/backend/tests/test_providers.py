from app.providers.images.comfyui import fill_tokens
from app.providers.images.base import ImageRequest
from app.providers.images.placeholder import PlaceholderImageProvider


def test_comfy_tokens_keep_types():
    wf = {"3": {"inputs": {"seed": "{{seed}}", "text": "a {{prompt}} b", "w": "{{width}}"}}}
    out = fill_tokens(wf, {"seed": 42, "prompt": "fox", "width": 640})
    assert out["3"]["inputs"] == {"seed": 42, "text": "a fox b", "w": 640}


def test_placeholder_is_deterministic():
    p = PlaceholderImageProvider()
    req = ImageRequest(kind="scene", prompt="x", negative_prompt="", seed=7, width=320, height=180,
                       hints={"title": "t", "characters": [{"name": "Mira", "palette": ["#112233", "#ffeedd"]}]})
    assert p.generate(req) == p.generate(req)
    req2 = ImageRequest(**{**req.__dict__, "seed": 8})
    assert p.generate(req2) != p.generate(req)
