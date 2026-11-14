#!/usr/bin/env python3
"""Transcribe, pad, and translate subtitles for a local video."""
import argparse
import subprocess
import sys
from pathlib import Path


PADDING_SERVICE = Path(__file__).resolve().with_name("subtitle_padding.py")
TRANSLATION_SERVICE = Path(__file__).resolve().with_name("subtitle_translate.py")


def call_elevate(video_file):
    subprocess.run(
        ["elevate", "transcribe", str(video_file)],
        cwd=video_file.parent,
        check=True,
    )
    subtitle_file = video_file.with_suffix(".srt")
    if not subtitle_file.is_file():
        raise RuntimeError(f"transcription did not create: {subtitle_file}")
    return subtitle_file


def call_subtitle_padding(subtitle_file):
    subprocess.run(
        [
            sys.executable,
            str(PADDING_SERVICE),
            str(subtitle_file),
        ],
        check=True,
    )


def call_subtitle_translate(source_subtitle, translated_subtitle):
    subprocess.run(
        [
            sys.executable,
            str(TRANSLATION_SERVICE),
            str(source_subtitle),
            str(translated_subtitle),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_file", type=Path)
    video_file = parser.parse_args().video_file.expanduser().resolve()
    if not video_file.is_file():
        raise ValueError(f"video file does not exist: {video_file}")

    source_subtitle = call_elevate(video_file)
    call_subtitle_padding(source_subtitle)
    call_subtitle_translate(
        source_subtitle,
        video_file.with_name(f"{video_file.stem}.en.srt"),
    )


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        ValueError,
    ) as error:
        raise SystemExit(f"Subtitle workflow failed: {error}") from error
