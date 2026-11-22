#!/usr/bin/env python3
"""Cut local product-trailer media into a verified H.264 MP4."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

STILL_SUFFIXES = {".png", ".jpeg", ".jpg", ".webp"}
ENCODE = ("-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p")


def number(value, name, minimum):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be a number >= {minimum}")
    return value


def integer(value, name, minimum):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def media(folder, name):
    path = (folder / name).resolve()
    if not path.is_file():
        raise ValueError(f"Missing media file: {path}")
    return path


def ffmpeg(executable, folder, *arguments):
    command = [executable, "-hide_banner", "-nostdin", "-loglevel", "error", *map(str, arguments)]
    subprocess.run(command, cwd=folder, stdout=subprocess.DEVNULL, check=True)


def frame_count(executable, folder, source, include_audio=False):
    streams = ["-map", "0:v:0"]
    if include_audio:
        streams += ["-map", "0:a:0?"]
    progress = subprocess.check_output(
        [executable, "-hide_banner", "-nostdin", "-loglevel", "error", "-xerror",
         "-progress", "pipe:1", "-nostats", "-i", str(source), *streams, "-f", "null", "-"],
        cwd=folder, text=True,
    )
    return int(re.findall(r"^frame=(\d+)$", progress, re.MULTILINE)[-1])


def picture_filter(shot, width, height, fps):
    left, top, right, bottom = [integer(v, "inset", 0) for v in shot.get("inset", [0, 0, 0, 0])]
    inner_width, inner_height = width - left - right, height - top - bottom
    if inner_width < 2 or inner_height < 2 or any(v % 2 for v in (left, top, right, bottom)):
        raise ValueError("Insets must be even pixels with room for the picture")
    fit = shot.get("fit", "cover")
    speed = number(shot.get("speed", 1), "clip speed", 0.01)
    filters = [f"setpts=(PTS-STARTPTS)/{speed}", f"fps={fps}"]
    if fit == "cover":
        x, y = [number(v, "focus", 0) for v in shot.get("focus", [0.5, 0.5])]
        if max(x, y) > 1:
            raise ValueError("Focus values must be between 0 and 1")
        filters += [f"scale={inner_width}:{inner_height}:force_original_aspect_ratio=increase:force_divisible_by=2",
                    f"crop={inner_width}:{inner_height}:(iw-ow)*{x}:(ih-oh)*{y}"]
    elif fit == "contain":
        filters += [f"scale={inner_width}:{inner_height}:force_original_aspect_ratio=decrease:force_divisible_by=2",
                    f"pad={inner_width}:{inner_height}:(ow-iw)/2:(oh-ih)/2:color=0x12141a"]
    else:
        raise ValueError("Clip fit must be cover or contain")
    filters += [f"pad={width}:{height}:{left}:{top}:color=0x12141a", "setsar=1"]
    return ",".join(filters)


def render_clip(executable, temp, folder, name, shot, width, height, fps):
    source = media(folder, shot["file"])
    frames = round(number(shot["seconds"], "clip seconds", 1 / fps) * fps)
    start = number(shot.get("start", 0), "clip start", 0)
    if source.suffix.lower() in STILL_SUFFIXES:
        if start != 0:
            raise ValueError(f"A still cannot have a trim start: {source.name}")
        timing = ("-loop", "1", "-framerate", fps)
    else:
        timing = ("-ss", start)
    ffmpeg(executable, temp, *timing, "-i", source, "-map", "0:v:0", "-an",
           "-vf", picture_filter(shot, width, height, fps), "-frames:v", frames, *ENCODE, name)
    actual = frame_count(executable, temp, name)
    if actual != frames:
        raise ValueError(f"{source.name} provides {actual} of the requested {frames} frames; shorten the clip or adjust speed")
    return frames


def assemble(executable, manifest, destination, overwrite):
    spec = json.loads(manifest.read_text(encoding="utf-8-sig"))
    folder = manifest.parent
    width = integer(spec["width"], "width", 2)
    height = integer(spec["height"], "height", 2)
    fps = integer(spec.get("fps", 30), "fps", 1)
    if width % 2 or height % 2:
        raise ValueError("Width and height must be even for H.264 yuv420p output")
    if not isinstance(spec["clips"], list) or not spec["clips"]:
        raise ValueError("The timeline needs at least one clip")
    caption_mode = spec.get("caption_mode", "track" if "captions" in spec else "none")
    if caption_mode not in {"none", "track", "burn"}:
        raise ValueError("caption_mode must be none, track, or burn")
    audio = media(folder, spec["audio"]) if "audio" in spec else None
    captions = media(folder, spec["captions"]) if caption_mode != "none" else None
    if captions and captions.suffix.lower() != ".srt":
        raise ValueError("The captions input must be a UTF-8 SRT file")
    if destination.suffix.lower() != ".mp4":
        raise ValueError("The output must be an MP4 file")
    if destination.exists() and not overwrite:
        raise ValueError("Output already exists; specify another destination or pass --overwrite")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".trailer-", dir=destination.parent) as temp:
        temp = Path(temp)
        names = [f"shot-{i:03d}.mp4" for i in range(len(spec["clips"]))]
        frames = sum(render_clip(executable, temp, folder, name, shot, width, height, fps)
                     for name, shot in zip(names, spec["clips"]))
        seconds = frames / fps
        (temp / "concat.txt").write_text("".join(f"file '{name}'\n" for name in names), encoding="ascii")
        inputs = ["-f", "concat", "-safe", 1, "-i", "concat.txt"]
        maps = ["-map", "0:v:0"]
        audio_index = 1
        if audio:
            inputs += ["-i", audio]
            maps += ["-map", "1:a:0", "-af", "apad", "-c:a", "aac", "-ar", "48000", "-b:a", "160k"]
            audio_index = 2

        video = ["-c:v", "copy"]
        if caption_mode == "track":
            inputs += ["-i", captions]
            maps += ["-map", f"{audio_index}:s:0", "-c:s", "mov_text"]
        elif caption_mode == "burn":
            shutil.copyfile(captions, temp / "captions.srt")
            font = spec.get("caption_font", "sans-serif")
            if not re.fullmatch(r"[\w .-]+", font):
                raise ValueError("caption_font must be a font family name")
            bottom = number(spec.get("caption_bottom", 0.16 if height > width else 0.06), "caption_bottom", 0)
            if bottom >= 0.5:
                raise ValueError("caption_bottom must be less than 0.5")
            margin = round(bottom * 288)
            size = 8.5 if height > width else 10
            style = f"FontName={font},FontSize={size},Alignment=2,MarginV={margin},Outline=1.5,Shadow=0"
            video = ["-vf", f"subtitles=captions.srt:force_style='{style}'", *ENCODE]

        ffmpeg(executable, temp, *inputs, *maps, *video, "-t", seconds, "-movflags", "+faststart", "final.mp4")
        decoded = frame_count(executable, temp, "final.mp4", include_audio=True)
        if decoded != frames:
            raise ValueError(f"Decoded {decoded} of {frames} expected frames")
        if overwrite:
            os.replace(temp / "final.mp4", destination)
        else:
            os.link(temp / "final.mp4", destination)
    print(f"PASS: {width}x{height} at {fps} fps, {frames} frames, {seconds:.2f}s, captions={caption_mode}, audio={'yes' if audio else 'no'}")
    print(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("timeline", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    executable = shutil.which(args.ffmpeg)
    if executable is None:
        parser.error("FFmpeg not found; pass --ffmpeg with an executable path")
    try:
        assemble(Path(executable).resolve(), args.timeline.resolve(), args.output.resolve(), args.overwrite)
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Render failed: {error}\n")


if __name__ == "__main__":
    main()
