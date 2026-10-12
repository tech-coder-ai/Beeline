"""Timeline: the exact, language-specific schedule the renderer executes.

Scene order and visuals come from the (language-independent) scene spec;
timing comes from the *measured* duration of that language's audio. A Hindi
line that runs longer than the English one simply makes that scene longer.
"""
from __future__ import annotations

import textwrap
from dataclasses import asdict, dataclass, field


@dataclass
class TimelineSegment:
    segment_id: str
    speaker: str
    speaker_name: str
    text: str
    audio_path: str
    start: float
    end: float


@dataclass
class TimelineScene:
    scene_id: str
    sequence: int
    title: str
    image_path: str
    image_checksum: str
    start: float
    end: float
    camera_movement: str
    segments: list[TimelineSegment] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


@dataclass
class SubtitleEvent:
    index: int
    start: float
    end: float
    text: str


@dataclass
class Timeline:
    language: str
    width: int
    height: int
    fps: int
    duration: float
    scenes: list[TimelineScene]
    subtitles: list[SubtitleEvent]

    def to_dict(self) -> dict:
        return asdict(self)


def build_timeline(*, language: str, width: int, height: int, fps: int, scenes: list[dict], segments: list[dict],
                   names: dict[str, str], padding: float, gap: float, min_scene: float) -> Timeline:
    """scenes: [{scene_id, sequence, title, image_path, image_checksum, planned, camera_movement}]
    segments: [{segment_id, scene_id, order, speaker, text, audio_path, duration}]"""
    by_scene: dict[str, list[dict]] = {}
    for seg in sorted(segments, key=lambda s: s["order"]):
        by_scene.setdefault(seg["scene_id"], []).append(seg)
    t = 0.0
    out_scenes: list[TimelineScene] = []
    for sc in sorted(scenes, key=lambda s: s["sequence"]):
        segs = by_scene.get(sc["scene_id"], [])
        speech = sum(s["duration"] for s in segs) + gap * max(0, len(segs) - 1)
        dur = max(min_scene, speech + 2 * padding) if segs else max(min_scene, sc["planned"])
        # snap to whole frames so video and audio never drift apart
        dur = round(round(dur * fps) / fps, 3)
        ts = TimelineScene(scene_id=sc["scene_id"], sequence=sc["sequence"], title=sc["title"],
                           image_path=sc["image_path"], image_checksum=sc["image_checksum"], start=round(t, 3),
                           end=round(t + dur, 3), camera_movement=sc["camera_movement"])
        cursor = t + padding
        for s in segs:
            ts.segments.append(TimelineSegment(segment_id=s["segment_id"], speaker=s["speaker"],
                                               speaker_name=names.get(s["speaker"], ""), text=s["text"],
                                               audio_path=s["audio_path"], start=round(cursor, 3),
                                               end=round(cursor + s["duration"], 3)))
            cursor += s["duration"] + gap
        out_scenes.append(ts)
        t += dur
    return Timeline(language=language, width=width, height=height, fps=fps, duration=round(t, 3),
                    scenes=out_scenes, subtitles=subtitle_events(out_scenes))


def subtitle_events(scenes: list[TimelineScene], max_chars: int = 84) -> list[SubtitleEvent]:
    """Split long segments into readable cues (<= 2 lines of ~42 chars), timed by character share."""
    events: list[SubtitleEvent] = []
    for sc in scenes:
        for seg in sc.segments:
            label = f"[{seg.speaker_name}] " if seg.speaker != "narrator" and seg.speaker_name else ""
            chunks = _cue_chunks(seg.text, max_chars)
            total = sum(len(c) for c in chunks)
            start = seg.start
            for i, chunk in enumerate(chunks):
                share = (seg.end - seg.start) * len(chunk) / max(1, total)
                end = seg.end if i == len(chunks) - 1 else start + share
                text = "\n".join(textwrap.wrap((label if i == 0 else "") + chunk, 42, break_long_words=False))
                events.append(SubtitleEvent(index=len(events) + 1, start=round(start, 3), end=round(end, 3), text=text))
                start = end
    return events


def _cue_chunks(text: str, max_chars: int) -> list[str]:
    """Prefer sentence boundaries; only wrap inside a sentence when it is too long for one cue."""
    import re
    chunks: list[str] = []
    for sentence in re.split(r"(?<=[.!?;:])\s+", text.strip()):
        if chunks and len(chunks[-1]) + 1 + len(sentence) <= max_chars:
            chunks[-1] += " " + sentence
        else:
            chunks.extend(textwrap.wrap(sentence, max_chars, break_long_words=False) or [sentence])
    return chunks or [text]


def _ts(seconds: float, sep: str = ",") -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(events: list[SubtitleEvent]) -> str:
    return "\n".join(f"{e.index}\n{_ts(e.start)} --> {_ts(e.end)}\n{e.text}\n" for e in events)


def to_vtt(events: list[SubtitleEvent]) -> str:
    return "WEBVTT\n\n" + "\n".join(f"{_ts(e.start, '.')} --> {_ts(e.end, '.')}\n{e.text}\n" for e in events)


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    def secs(ts: str) -> float:
        hms, ms = ts.strip().split(",")
        h, m, s = (int(x) for x in hms.split(":"))
        return h * 3600 + m * 60 + s + int(ms) / 1000
    cues = []
    for block in [b for b in text.strip().split("\n\n") if b.strip()]:
        lines = block.strip().splitlines()
        if len(lines) >= 2 and "-->" in lines[1]:
            a, b = lines[1].split("-->")
            cues.append((secs(a), secs(b), "\n".join(lines[2:])))
    return cues


def chapters(scenes: list[TimelineScene]) -> list[tuple[float, str]]:
    """YouTube chapters: start at 0:00, at least 3, each >= 10 s. Merge short scenes into the previous chapter."""
    out: list[tuple[float, str]] = []
    for sc in scenes:
        if not out or sc.start - out[-1][0] >= 10:
            out.append((sc.start, sc.title or f"Part {len(out) + 1}"))
    if len(out) >= 3 and scenes[-1].end - out[-1][0] >= 10:
        return out
    return []


def fmt_chapter(t: float) -> str:
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
