"""FFmpeg renderer. The application decides *what* happens (the timeline); FFmpeg does the pixels.

Render plan for one language:
  1. one clip per scene: still image -> Ken Burns move (or the AI motion clip), extended by the
     transition length so neighbouring clips can overlap. Clips are cached by fingerprint.
  2. one narration track: every segment placed at its absolute start time (adelay + amix)
  3. optional music bed, ducked under the narration (sidechaincompress)
  4. final pass: crossfade clips (xfade) + burned subtitles + soft subtitle track, loudness-normalised
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app.config import VideoCfg
from app.media import fingerprint, run_ffmpeg
from app.services.rendering.timeline import Timeline, TimelineScene

FADE = 0.5          # fade from/to black at the very start and end of the video
AUDIO_RATE = 48000


def _motion(movement: str, zoom: float, frames: int) -> tuple[str, str, str]:
    d = max(1, frames - 1)
    center_x, center_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if movement == "slow_push_in":
        return f"1+({zoom}-1)*on/{d}", center_x, center_y
    if movement == "slow_pull_out":
        return f"{zoom}-({zoom}-1)*on/{d}", center_x, center_y
    if movement == "pan_left":
        return f"{zoom}", f"(iw-iw/zoom)*(1-on/{d})", center_y
    if movement == "pan_right":
        return f"{zoom}", f"(iw-iw/zoom)*on/{d}", center_y
    return "1", "0", "0"


def transition_seconds(cfg: VideoCfg) -> float:
    return 0.0 if cfg.transition == "none" else cfg.transition_seconds


def clip_fingerprint(scene: TimelineScene, cfg: VideoCfg, extend: float = 0.0, fade_in: bool = False,
                     fade_out: bool = False) -> str:
    return fingerprint("clip-v3", scene.image_checksum, scene.motion_checksum, scene.duration, scene.camera_movement,
                       cfg.width, cfg.height, cfg.fps, cfg.crf, cfg.preset, cfg.camera_zoom, extend, fade_in, fade_out)


def _fades(length: float, fade_in: bool, fade_out: bool) -> str:
    f = []
    if fade_in:
        f.append(f"fade=t=in:st=0:d={FADE}")
    if fade_out:
        f.append(f"fade=t=out:st={max(0.0, length - FADE):.3f}:d={FADE}")
    return ("," + ",".join(f)) if f else ""


def render_clip(scene: TimelineScene, cfg: VideoCfg, out: Path, extend: float = 0.0, fade_in: bool = False,
                fade_out: bool = False) -> None:
    """Render one scene clip of length scene.duration + extend (the extra overlaps the next scene's crossfade)."""
    w, h, fps = cfg.width, cfg.height, cfg.fps
    length = scene.duration + extend
    frames = max(1, round(length * fps))
    if scene.motion_path:
        # AI clip -> output size/fps; if the narration is longer than the clip, hold the last frame.
        vf = (f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
              f"tpad=stop_mode=clone:stop_duration={length:.3f},trim=duration={length:.3f}"
              f"{_fades(length, fade_in, fade_out)},format=yuv420p")
        src = scene.motion_path
    else:
        z, x, y = _motion(scene.camera_movement, cfg.camera_zoom, frames)
        # Upscale 2x before zoompan: zooming a small frame produces visible jitter.
        vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
              f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},setsar=1"
              f"{_fades(length, fade_in, fade_out)},format=yuv420p")
        src = scene.image_path
    run_ffmpeg(["-i", src, "-vf", vf, "-frames:v", str(frames), "-r", str(fps),
                "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-pix_fmt", "yuv420p",
                "-an", str(out)])


def render_narration(timeline: Timeline, out: Path) -> None:
    segs = [s for sc in timeline.scenes for s in sc.segments]
    if not segs:
        run_ffmpeg(["-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo", "-t", f"{timeline.duration:.3f}",
                    "-c:a", "pcm_s16le", str(out)])
        return
    args: list[str] = []
    parts: list[str] = []
    for i, s in enumerate(segs):
        args += ["-i", s.audio_path]
        ms = int(round(s.start * 1000))
        parts.append(f"[{i}:a]aresample={AUDIO_RATE},adelay=delays={ms}:all=1[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(segs)))
    graph = ";".join(parts) + f";{mix}amix=inputs={len(segs)}:normalize=0:duration=longest,apad," \
                              f"atrim=0:{timeline.duration:.3f},aformat=channel_layouts=stereo[out]"
    _run_graph(args, graph, ["-map", "[out]", "-c:a", "pcm_s16le", str(out)])


def _run_graph(inputs: list[str], graph: str, outputs: list[str]) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(graph)  # long graphs go in a script file, not the command line
        script = f.name
    try:
        run_ffmpeg([*inputs, "-filter_complex_script", script, *outputs])
    finally:
        Path(script).unlink(missing_ok=True)


def _escape_filter_path(p: Path) -> str:
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def subtitle_style(cfg: VideoCfg) -> str:
    # libass scales SRT styles against a 288-px-tall virtual canvas, so these numbers are resolution-independent.
    # BorderStyle=3 draws a translucent box behind each line (the modern caption look) instead of an outline.
    return (f"FontName={cfg.subtitle_font},Bold=1,FontSize=12,PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H80000000,BackColour=&H80000000,BorderStyle=3,Outline=5,Shadow=0,MarginV=18")


def render_final(timeline: Timeline, clips: list[Path], narration: Path, srt: Path, cfg: VideoCfg, out: Path,
                 music: Path | None = None, workdir: Path | None = None) -> None:
    t = transition_seconds(cfg)
    args: list[str] = []
    for c in clips:
        args += ["-i", str(c)]
    n = len(clips)
    args += ["-i", str(narration)]
    nar = n
    if music:
        args += ["-stream_loop", "-1", "-i", str(music)]
    args += ["-i", str(srt)]
    srt_index = n + (2 if music else 1)

    # video: crossfade each clip into the next at the next scene's start time
    vparts = [f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[c{i}]" for i in range(n)]
    last = "c0"
    for i in range(1, n):
        offset = timeline.scenes[i].start
        if t > 0:
            vparts.append(f"[{last}][c{i}]xfade=transition={cfg.transition}:duration={t}:offset={offset:.3f}[x{i}]")
        else:
            vparts.append(f"[{last}][c{i}]concat=n=2:v=1:a=0[x{i}]")
        last = f"x{i}"
    if cfg.burn_subtitles:
        vparts.append(f"[{last}]subtitles='{_escape_filter_path(srt)}':force_style='{subtitle_style(cfg)}'[vout]")
    else:
        vparts.append(f"[{last}]null[vout]")

    if music:
        aparts = [f"[{nar}:a]asplit=2[nar][key]", f"[{nar + 1}:a]aresample={AUDIO_RATE},volume={cfg.music_volume}[mus]",
                  "[mus][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]",
                  f"[nar][duck]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-16:TP=-1.5:LRA=11,aresample={AUDIO_RATE}[aout]"]
    else:
        aparts = [f"[{nar}:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample={AUDIO_RATE}[aout]"]

    _run_graph(args, ";".join(vparts + aparts), [
        "-map", "[vout]", "-map", "[aout]", "-map", f"{srt_index}:s",
        "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-c:s", "mov_text",
        "-metadata:s:s:0", f"language={_iso639_2(timeline.language)}",
        "-t", f"{timeline.duration:.3f}", "-movflags", "+faststart", str(out)])


def _iso639_2(code: str) -> str:
    return {"en": "eng", "hi": "hin", "es": "spa", "fr": "fra", "de": "deu", "it": "ita", "pt": "por",
            "ja": "jpn", "zh": "zho", "ar": "ara", "bn": "ben", "ta": "tam", "te": "tel", "mr": "mar"}.get(code, "und")


def copy_clip(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
