#!/usr/bin/env python3
"""Select the next unprocessed playlist video and record completed videos."""
import json
import os
import subprocess
import sys
import tempfile


def playlist_video_ids(playlist_id):
    playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--print",
                "%(id)s",
                playlist_url,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise SystemExit("yt-dlp is required to read playlist videos") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or str(error)
        raise SystemExit(f"Could not read playlist with yt-dlp: {message}") from error
    return [
        video_id
        for video_id in result.stdout.splitlines()
        if video_id and video_id != "NA"
    ]


def load_history(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as history_file:
            history = json.load(history_file)
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Could not read download history {path}: {error}") from error
    if not isinstance(history, dict) or any(
        not isinstance(ids, list)
        or any(not isinstance(video_id, str) for video_id in ids)
        for ids in history.values()
    ):
        raise SystemExit(f"Invalid download history format: {path}")
    return history


def write_history(path, history):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory, delete=False
        ) as history_file:
            temp_path = history_file.name
            json.dump(history, history_file, indent=2)
            history_file.write("\n")
        os.replace(temp_path, path)
    except OSError as error:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise SystemExit(f"Could not save download history {path}: {error}") from error


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: playlist_history.py next|mark ...")
    command = sys.argv[1]
    if command not in {"next", "mark"}:
        raise SystemExit("Usage: playlist_history.py next|mark ...")
    if command == "next":
        if len(sys.argv) != 4:
            raise SystemExit(
                "Usage: playlist_history.py next <playlist_id> <history.json>"
            )
        playlist_id, history_path = sys.argv[2:4]
        history = load_history(history_path)
        processed = set(history.get(playlist_id, []))
        video_id = next(
            (item for item in playlist_video_ids(playlist_id) if item not in processed),
            "",
        )
        print(video_id)
        return

    if len(sys.argv) != 5:
        raise SystemExit(
            "Usage: playlist_history.py mark <playlist_id> <video_id> <history.json>"
        )
    playlist_id, video_id, history_path = sys.argv[2:5]
    history = load_history(history_path)
    processed = history.setdefault(playlist_id, [])
    if video_id not in processed:
        processed.append(video_id)
        write_history(history_path, history)


if __name__ == "__main__":
    main()
