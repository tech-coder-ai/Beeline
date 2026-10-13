from app.services.rendering.timeline import build_timeline, chapters, parse_srt, to_srt


def _tl(durations, gap=0.5, pad=1.0):
    scenes = [{"scene_id": f"scene_{i:03d}", "sequence": i, "title": f"S{i}", "image_path": "x.png",
               "image_checksum": "c", "planned": 5, "camera_movement": "static"} for i in range(1, len(durations) + 1)]
    segs, order = [], 0
    for i, ds in enumerate(durations, start=1):
        for j, d in enumerate(ds):
            segs.append({"segment_id": f"scene_{i:03d}_l{j:02d}", "scene_id": f"scene_{i:03d}", "order": order,
                         "speaker": "narrator" if j == 0 else "char_001", "text": "word " * int(d * 3),
                         "audio_path": "a.wav", "duration": d})
            order += 1
    return build_timeline(language="en", width=320, height=180, fps=24, scenes=scenes, segments=segs,
                          names={"char_001": "Mira"}, padding=pad, gap=gap, min_scene=4)


def test_scene_length_follows_measured_audio():
    tl = _tl([[3.0, 2.0], [1.0]])
    s1, s2 = tl.scenes
    assert s1.duration == 1.0 + 3.0 + 0.5 + 2.0 + 1.0   # pad + seg + gap + seg + pad
    assert s2.duration == 4.0                           # min scene length wins
    assert s1.segments[1].start == 1.0 + 3.0 + 0.5
    assert tl.duration == s1.duration + s2.duration


def test_subtitles_are_sequential_labelled_and_round_trip():
    tl = _tl([[6.0, 4.0], [5.0]])
    cues = parse_srt(to_srt(tl.subtitles))
    assert len(cues) == len(tl.subtitles)
    assert all(b[0] >= a[1] - 1e-3 for a, b in zip(cues, cues[1:]))
    assert any(c[2].startswith("[Mira]") for c in cues)


def test_chapters_follow_youtube_rules():
    assert chapters(_tl([[3.0]] * 2).scenes) == []          # too few / too short
    ch = chapters(_tl([[12.0]] * 4).scenes)
    assert ch[0][0] == 0 and len(ch) >= 3


def test_title_card_is_not_subtitled():
    from app.services.rendering.timeline import subtitle_events
    tl = _tl([[2.0], [3.0]])
    tl.scenes[0].scene_id = "intro"
    events = subtitle_events(tl.scenes)
    assert len(events) == 1 and events[0].start >= tl.scenes[1].start


def test_visual_prompts_use_words_not_hex_codes():
    from app.schemas.story import Appearance, CharacterProfile
    from app.services.visual_prompts import character_prompt, color_name, scene_prompt
    lion = CharacterProfile(character_id="char_001", name="Lion",
                            appearance=Appearance(species="lion", palette=["#d4a017", "#8b5a2b"]))
    assert color_name("#d4a017") == "golden"
    p = scene_prompt("watercolor", "The lion sleeps", [lion], "savanna", "wide", "peaceful", ["keep #fff"])
    assert "#" not in p and p.startswith("a lion (golden, brown tones)") and "The lion sleeps" in p
    assert "#" not in character_prompt("watercolor", lion)
