#!/usr/bin/env python3
"""Read and validate the daily workflow's key=value configuration."""
import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SCRIPT_DIR / "daily-impd.config"
REQUIRED = ("destination", "japanese_playlist_id", "chinese_playlist_id")


def read_settings(path):
    settings = {}
    with path.open(encoding="utf-8") as file:
        for number, raw_line in enumerate(file, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            name, value = name.strip(), value.strip()
            if not separator or not name or not value:
                raise ValueError(f"line {number} must use key=value format")
            if name not in REQUIRED and name != "download_history":
                raise ValueError(f"line {number} has unknown setting {name!r}")
            settings[name] = value

    missing = [name for name in REQUIRED if not settings.get(name)]
    if missing:
        raise ValueError(f"missing required setting(s): {', '.join(missing)}")
    settings.setdefault("download_history", ".daily-impd-history.json")
    return settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("get", "path"))
    parser.add_argument("name")
    args = parser.parse_args()
    path = Path(os.environ.get("IMPD_CONFIG", DEFAULT_CONFIG)).expanduser()

    try:
        settings = read_settings(path)
        if args.name not in settings:
            raise ValueError(f"unknown setting: {args.name}")
        value = settings[args.name]
        if args.command == "path":
            value = Path(value).expanduser()
            value = value if value.is_absolute() else path.resolve().parent / value
        print(value)
    except (OSError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
