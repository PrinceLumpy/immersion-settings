#!/usr/bin/env python3
"""Extract hardcoded subtitles from a video with VideoSubFinder and RapidVideOCR."""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_file", type=Path)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing SRT with the same name",
    )
    args = parser.parse_args()

    video_file = args.video_file.expanduser().resolve()
    if not video_file.is_file():
        raise ValueError(f"video file does not exist: {video_file}")

    output_file = video_file.with_suffix(".srt")
    if output_file.exists() and not args.force:
        raise FileExistsError(
            f"{output_file} already exists; pass --force to replace it"
        )

    for command in ("videosubfinder", "rapid_videocr"):
        if shutil.which(command) is None:
            raise RuntimeError(f"required command is not on PATH: {command}")

    with tempfile.TemporaryDirectory(
        prefix=f".{video_file.stem}.videosubfinder-",
        dir=video_file.parent,
    ) as work_dir:
        subprocess.run(
            [
                "videosubfinder",
                "-r",
                "-i",
                str(video_file),
                "-o",
                work_dir,
            ],
            check=True,
        )

        rgb_images = Path(work_dir) / "RGBImages"
        if not rgb_images.is_dir():
            raise RuntimeError(f"VideoSubFinder did not create {rgb_images}")

        subprocess.run(
            [
                "rapid_videocr",
                "-i",
                str(rgb_images),
                "-s",
                str(video_file.parent),
                "-f",
                video_file.stem,
                "-o",
                "srt",
            ],
            check=True,
        )

    if not output_file.is_file():
        raise RuntimeError(f"RapidVideOCR did not create {output_file}")
    print(f"Created {output_file}")


if __name__ == "__main__":
    try:
        main()
    except (
        FileExistsError,
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        ValueError,
    ) as error:
        raise SystemExit(f"Subtitle extraction failed: {error}") from error
