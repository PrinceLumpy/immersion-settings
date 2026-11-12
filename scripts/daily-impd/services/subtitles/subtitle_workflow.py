#!/usr/bin/env python3
"""Transcribe, translate, and embed subtitles for a local video."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


PADDING_SERVICE = Path(__file__).resolve().with_name("subtitle_padding.py")
TRANSLATION_SERVICE = Path(__file__).resolve().with_name("subtitle_translate.py")
SOURCE_LANGUAGES = {
    "jp": {
        "captions": ("ja", "jp"),
        "elevate": "ja",
        "container": "jpn",
    },
    "zh": {
        "captions": ("zh-Hans", "zh-CN", "zh"),
        "elevate": "zh",
        "container": "zho",
    },
}


def run(command, *, cwd=None):
    subprocess.run(command, cwd=cwd, check=True)


def find_subtitle(video_base, language_codes):
    for language in language_codes:
        candidates = [video_base.with_name(f"{video_base.name}.{language}.srt")]
        candidates.extend(
            sorted(video_base.parent.glob(f"{video_base.name}.{language}.*.srt"))
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    return None


def fetch_youtube_subtitles(video_base, youtube_url, source_language):
    language_codes = SOURCE_LANGUAGES[source_language]["captions"]
    languages = ",".join((*language_codes, "en.*"))
    print(f"Checking YouTube for {source_language} and English subtitles.")
    run(
        [
            "yt-dlp",
            "--ignore-config",
            "--no-playlist",
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            languages,
            "--sub-format",
            "srt/vtt",
            "--convert-subs",
            "srt",
            "--output",
            f"{video_base}.%(ext)s",
            youtube_url,
        ]
    )
    return language_codes


def validate_youtube_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
    }:
        raise ValueError("daily subtitle URL must be an HTTPS YouTube URL")


def create_source_subtitle(video_file, video_base, source_language):
    command = ["elevate"]
    if source_language:
        command.extend(["--language", SOURCE_LANGUAGES[source_language]["elevate"]])
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
    return subtitle_file


def embed_subtitles(video_file, source_subtitle, english_subtitle, source_language):
    output_file = video_file.with_suffix(".mkv")
    if output_file != video_file and output_file.exists():
        raise FileExistsError(
            f"cannot embed subtitles: output file already exists: {output_file}"
        )
    source_track_metadata = []
    if source_language:
        source_track_language = SOURCE_LANGUAGES[source_language]["container"]
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

        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "s",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(temporary_file),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subtitle_tracks = [
            line for line in probe.stdout.splitlines() if line.strip()
        ]
        if len(subtitle_tracks) < 2:
            raise RuntimeError(
                "subtitle verification failed: expected source and English "
                f"tracks, found {len(subtitle_tracks)}"
            )

        os.replace(temporary_file, output_file)
        if video_file != output_file:
            video_file.unlink()
    finally:
        if temporary_file is not None:
            temporary_file.unlink(missing_ok=True)

    print(f"Embedded source and English subtitles in: {output_file}")


def cleanup_temporary_subtitles(
    video_base, source_subtitle, english_subtitle, source_language
):
    transcript_file = video_base.with_name(f"{video_base.name}.transcript.json")
    language_codes = (
        SOURCE_LANGUAGES[source_language]["captions"]
        if source_language
        else ()
    )
    temporary_files = {
        source_subtitle,
        english_subtitle,
        transcript_file,
    }
    for subtitle in (
        find_subtitle(video_base, (*language_codes, "en")),
    ):
        if subtitle is not None:
            temporary_files.add(subtitle)
    for language in (*language_codes, "en"):
        temporary_files.update(
            video_base.parent.glob(f"{video_base.name}.{language}.*.srt")
        )
    print("Translation and embedding succeeded; cleaning up temporary subtitle files.")
    for path in temporary_files:
        if path.exists():
            path.unlink()


def run_daily_workflow(video_file, youtube_url, source_language):
    if source_language not in SOURCE_LANGUAGES:
        raise ValueError("daily subtitle language must be 'jp' or 'zh'")
    validate_youtube_url(youtube_url)
    if not video_file.is_file():
        raise ValueError(f"video file does not exist: {video_file}")

    video_base = video_file.with_suffix("")
    language_codes = fetch_youtube_subtitles(
        video_base, youtube_url, source_language
    )
    source_subtitle = find_subtitle(video_base, language_codes)
    english_subtitle = find_subtitle(video_base, ("en",))

    if source_subtitle is None:
        print("No target-language YouTube subtitles found; transcribing with elevate.")
        source_subtitle = create_source_subtitle(
            video_file, video_base, source_language
        )
        english_subtitle = None
    else:
        print(f"Using target-language YouTube subtitles: {source_subtitle}")

    if english_subtitle is None:
        english_subtitle = video_base.with_name(f"{video_base.name}.en.srt")
        print("No usable English subtitles found; translating with OpenRouter.")
        run(
            [
                sys.executable,
                str(TRANSLATION_SERVICE),
                str(source_subtitle),
                str(english_subtitle),
            ]
        )
    else:
        print(f"Using English YouTube subtitles: {english_subtitle}")

    embed_subtitles(
        video_file, source_subtitle, english_subtitle, source_language
    )
    cleanup_temporary_subtitles(
        video_base, source_subtitle, english_subtitle, source_language
    )


def run_workflow(video_file, source_language=None):
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
    print("Translating the complete subtitle file into English with OpenRouter.")
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
    cleanup_temporary_subtitles(
        video_base, source_subtitle, english_subtitle, source_language
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_file", type=Path)
    parser.add_argument(
        "source_language",
        choices=tuple(SOURCE_LANGUAGES),
        nargs="?",
        help="optional source subtitle language code (jp or zh)",
    )
    parser.add_argument(
        "--youtube-url",
        help="enable daily mode: fetch target-language and English captions first",
    )
    args = parser.parse_args()
    video_file = args.video_file.expanduser().resolve()
    if args.youtube_url:
        if not args.source_language:
            parser.error("--youtube-url requires a source language argument")
        run_daily_workflow(video_file, args.youtube_url, args.source_language)
    else:
        run_workflow(video_file, args.source_language)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Subtitle workflow failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
