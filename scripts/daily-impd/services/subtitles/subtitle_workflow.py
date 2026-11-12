#!/usr/bin/env python3
"""Transcribe, translate, and embed subtitles for a local video."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


PADDING_SERVICE = Path(__file__).resolve().with_name("subtitle_padding.py")
TRANSLATION_SERVICE = Path(__file__).resolve().with_name("subtitle_translate.py")


def run(command, *, cwd=None):
    subprocess.run(command, cwd=cwd, check=True)


def create_source_subtitle(video_file, video_base):
    run(["elevate", "transcribe", str(video_file)], cwd=video_file.parent)
    subtitle_file = video_base.with_name(f"{video_base.name}.srt")
    if not subtitle_file.is_file():
        raise RuntimeError(
            f"transcription did not create the expected file: {subtitle_file}"
        )

    run([sys.executable, str(PADDING_SERVICE), str(subtitle_file), str(subtitle_file)])
    transcript_file = video_base.with_name(f"{video_base.name}.transcript.json")
    if transcript_file.exists():
        transcript_file.unlink()
    return subtitle_file


def embed_subtitles(video_file, source_subtitle, english_subtitle):
    output_file = video_file.with_suffix(".mkv")
    if output_file != video_file and output_file.exists():
        raise FileExistsError(
            f"cannot embed subtitles: output file already exists: {output_file}"
        )

    temporary_file = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".mkv",
            prefix=f".{output_file.stem}.",
            dir=output_file.parent,
            delete=False,
        ) as temporary:
            temporary_file = Path(temporary.name)

        run(
            [
                "ffmpeg",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video_file),
                "-i",
                str(source_subtitle),
                "-i",
                str(english_subtitle),
                "-map",
                "0:v?",
                "-map",
                "0:a?",
                "-map",
                "1:0",
                "-map",
                "2:0",
                "-map_metadata",
                "0",
                "-map_chapters",
                "0",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-c:s",
                "srt",
                "-metadata:s:s:0",
                "title=Original",
                "-metadata:s:s:1",
                "language=eng",
                "-metadata:s:s:1",
                "title=English",
                str(temporary_file),
            ]
        )
        if not temporary_file.is_file() or temporary_file.stat().st_size == 0:
            raise RuntimeError("ffmpeg did not create the subtitle-embedded video")
        os.replace(temporary_file, output_file)
        if video_file != output_file:
            video_file.unlink()
    finally:
        if temporary_file is not None:
            temporary_file.unlink(missing_ok=True)

    print(f"Embedded source and English subtitles in: {output_file}")


def run_workflow(video_file):
    if not video_file.is_file():
        raise ValueError(f"video file does not exist: {video_file}")

    video_base = video_file.with_suffix("")
    print("Transcribing video with elevate's automatic language detection.")
    source_subtitle = create_source_subtitle(video_file, video_base)

    english_subtitle = video_base.with_name(f"{video_base.name}.en.srt")
    print("Translating detected-language subtitles into English with Ollama.")
    run(
        [
            sys.executable,
            str(TRANSLATION_SERVICE),
            str(source_subtitle),
            str(english_subtitle),
        ]
    )
    embed_subtitles(video_file, source_subtitle, english_subtitle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_file", type=Path)
    args = parser.parse_args()
    run_workflow(args.video_file.expanduser().resolve())


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Subtitle workflow failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
