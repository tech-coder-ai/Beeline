"""FFmpeg renderer. The application decides *what* happens (the timeline); FFmpeg does the pixels.

Render plan for one language:
  1. one clip per scene: still image -> Ken Burns move -> short fade in/out
     (clips are cached by fingerprint and shared between languages when identical)
  2. one narration track: every segment placed at its absolute start time (adelay + amix)
  3. optional music bed, ducked under the narration (sidechaincompress)
  4. final mux: concat clips + audio (+ burned subtitles) + soft subtitle track, loudness-normalised
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app.config import VideoCfg
from app.media import fingerprint, run_ffmpeg
from app.services.rendering.timeline import Timeline, TimelineScene

FADE = 0.3
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


def clip_fingerprint(scene: TimelineScene, cfg: VideoCfg) -> str:
    return fingerprint("clip-v1", scene.image_checksum, scene.duration, scene.camera_movement, cfg.width, cfg.height,
                       cfg.fps, cfg.crf, cfg.preset, cfg.camera_zoom)


def render_clip(scene: TimelineScene, cfg: VideoCfg, out: Path) -> None:
    w, h, fps = cfg.width, cfg.height, cfg.fps
    frames = max(1, round(scene.duration * fps))
    z, x, y = _motion(scene.camera_movement, cfg.camera_zoom, frames)
    # Upscale 2x before zoompan: zooming a small frame produces visible jitter.
    vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},"
          f"fade=t=in:st=0:d={FADE},fade=t=out:st={max(0.0, scene.duration - FADE):.3f}:d={FADE},"
          f"format=yuv420p")
    run_ffmpeg(["-i", scene.image_path, "-vf", vf, "-frames:v", str(frames), "-r", str(fps),
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
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(graph)  # long graphs go in a script file, not the command line
        script = f.name
    try:
        run_ffmpeg([*args, "-filter_complex_script", script, "-map", "[out]", "-c:a", "pcm_s16le", str(out)])
    finally:
        Path(script).unlink(missing_ok=True)


def _escape_filter_path(p: Path) -> str:
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render_final(timeline: Timeline, clips: list[Path], narration: Path, srt: Path, cfg: VideoCfg, out: Path,
                 music: Path | None = None, workdir: Path | None = None) -> None:
    work = workdir or out.parent
    concat_list = work / "clips.txt"
    concat_list.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips))
    args = ["-f", "concat", "-safe", "0", "-i", str(concat_list), "-i", str(narration)]
    if music:
        args += ["-stream_loop", "-1", "-i", str(music)]
    args += ["-i", str(srt)]
    srt_index = 3 if music else 2
    if music:
        audio_graph = (f"[1:a]asplit=2[nar][key];[2:a]aresample={AUDIO_RATE},volume={cfg.music_volume}[mus];"
                       f"[mus][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];"
                       f"[nar][duck]amix=inputs=2:normalize=0:duration=first,")
    else:
        audio_graph = "[1:a]"
    audio_graph += f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample={AUDIO_RATE}[aout]"
    if cfg.burn_subtitles:
        # libass scales SRT styles against a 288-px-tall virtual canvas, not the real frame height,
        # so these numbers are resolution-independent (16 ~= 6% of frame height).
        style = "FontName=DejaVu Sans,FontSize=15,Outline=1.5,Shadow=0,MarginV=16,BorderStyle=1"
        video_graph = f"[0:v]subtitles='{_escape_filter_path(srt)}':force_style='{style}'[vout]"
        args += ["-filter_complex", f"{video_graph};{audio_graph}", "-map", "[vout]",
                 "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-pix_fmt", "yuv420p"]
    else:
        args += ["-filter_complex", audio_graph, "-map", "0:v", "-c:v", "copy"]
    args += ["-map", "[aout]", "-map", f"{srt_index}:s", "-c:a", "aac", "-b:a", "192k", "-c:s", "mov_text",
             "-metadata:s:s:0", f"language={_iso639_2(timeline.language)}",
             "-t", f"{timeline.duration:.3f}", "-movflags", "+faststart", str(out)]
    run_ffmpeg(args)


def _iso639_2(code: str) -> str:
    return {"en": "eng", "hi": "hin", "es": "spa", "fr": "fra", "de": "deu", "it": "ita", "pt": "por",
            "ja": "jpn", "zh": "zho", "ar": "ara", "bn": "ben", "ta": "tam", "te": "tel", "mr": "mar"}.get(code, "und")


def copy_clip(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
