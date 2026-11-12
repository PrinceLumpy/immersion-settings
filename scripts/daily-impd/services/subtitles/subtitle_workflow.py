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


def create_source_subtitle(video_file, video_base, source_language):
    command = ["elevate"]
    if source_language:
        command.extend(["--language", {"jp": "ja", "zh": "zh"}[source_language]])
    command.extend(["transcribe", str(video_file)])
    run(command, cwd=video_file.parent)
    generated_subtitle = video_base.with_name(f"{video_base.name}.srt")
    if not generated_subtitle.is_file():
        raise RuntimeError(
            f"transcription did not create the expected file: {generated_subtitle}"
        )

    subtitle_suffix = source_language or "transcript"
    subtitle_file = video_base.with_name(f"{video_base.name}.{subtitle_suffix}.srt")
    generated_subtitle.replace(subtitle_file)
    run([sys.executable, str(PADDING_SERVICE), str(subtitle_file), str(subtitle_file)])
    transcript_file = video_base.with_name(f"{video_base.name}.transcript.json")
    if transcript_file.exists():
        transcript_file.unlink()
    return subtitle_file


def embed_subtitles(video_file, source_subtitle, english_subtitle, source_language):
    output_file = video_file.with_suffix(".mkv")
    if output_file != video_file and output_file.exists():
        raise FileExistsError(
            f"cannot embed subtitles: output file already exists: {output_file}"
        )
    source_track_metadata = []
    if source_language:
        source_track_language = {"jp": "jpn", "zh": "zho"}[source_language]
        source_track_metadata = [
            "-metadata:s:s:0",
            f"language={source_track_language}",
        ]

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
                *source_track_metadata,
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


def run_workflow(video_file, source_language):
    if not video_file.is_file():
        raise ValueError(f"video file does not exist: {video_file}")

    video_base = video_file.with_suffix("")
    if source_language:
        print(f"Transcribing video in {source_language}.")
    else:
        print("Transcribing video with automatic language detection.")
    source_subtitle = create_source_subtitle(
        video_file, video_base, source_language
    )

    english_subtitle = video_base.with_name(f"{video_base.name}.en.srt")
    print("Translating source-language subtitles into English with Ollama.")
    run(
        [
            sys.executable,
            str(TRANSLATION_SERVICE),
            str(source_subtitle),
            str(english_subtitle),
        ]
    )
    embed_subtitles(
        video_file, source_subtitle, english_subtitle, source_language
    )
    source_subtitle.unlink()
    english_subtitle.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_file", type=Path)
    parser.add_argument(
        "source_language",
        choices=("jp", "zh"),
        nargs="?",
        help="optional source subtitle language code (jp or zh)",
    )
    args = parser.parse_args()
    run_workflow(args.video_file.expanduser().resolve(), args.source_language)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Subtitle workflow failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
