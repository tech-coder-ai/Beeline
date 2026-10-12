import json
from pathlib import Path

from app.schemas.story import Script, ScriptLine
from app.services.story.checks import check_script, has_errors, verbatim_overlap
from app.services.story.heuristic import adapt, detect_characters

SAMPLES = Path(__file__).resolve().parents[2] / "sample_stories"


def _sample(name):
    return json.loads((SAMPLES / f"{name}.json").read_text())


def test_detects_multi_word_characters():
    assert detect_characters(_sample("town_mouse_country_mouse")["text"]) == ["Country Mouse", "Town Mouse"]
    assert set(detect_characters(_sample("lion_and_mouse")["text"])) == {"Lion", "Mouse"}


def test_heuristic_script_attributes_dialogue_and_passes_checks():
    d = _sample("hare_and_tortoise")
    analysis, script = adapt(d["title"], d["author"], d["text"], target_scenes=6, min_s=4, max_s=40, style="s")
    ids = {c.name: c.character_id for c in analysis.characters}
    quote = next(l for sc in script.scenes for l in sc.lines if l.text.startswith("Though you be swift"))
    assert quote.speaker == ids["Tortoise"]
    assert [sc.sequence for sc in script.scenes] == list(range(1, len(script.scenes) + 1))
    issues = check_script(analysis, script, source_text=d["text"], min_s=4, max_s=40,
                          require_transformation=False, max_similarity=0.6)
    assert not has_errors(issues)


def test_checks_catch_unknown_speaker_and_duplicates():
    d = _sample("lion_and_mouse")
    analysis, script = adapt(d["title"], d["author"], d["text"], target_scenes=3, min_s=4, max_s=40, style="s")
    bad = script.model_copy(deep=True)
    bad.scenes[0].lines.append(ScriptLine(speaker="char_999", text="Who am I?"))
    bad.scenes.append(bad.scenes[0].model_copy())
    codes = {i.code for i in check_script(analysis, Script.model_validate(bad.model_dump()), source_text=d["text"],
                                          min_s=4, max_s=40, require_transformation=False, max_similarity=0.6)}
    assert {"unknown_speaker", "duplicate_scene", "sequence_gap"} <= codes


def test_verbatim_script_is_blocked_when_license_requires_transformation():
    d = _sample("lion_and_mouse")
    analysis, script = adapt(d["title"], d["author"], d["text"], target_scenes=3, min_s=4, max_s=40, style="s")
    assert verbatim_overlap(script, d["text"]) > 0.9
    issues = check_script(analysis, script, source_text=d["text"], min_s=4, max_s=40,
                          require_transformation=True, max_similarity=0.6)
    assert "too_close_to_source" in {i.code for i in issues if i.severity == "error"}
