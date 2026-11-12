#!/usr/bin/env python3
"""Read and validate the daily workflow's key=value configuration."""
import argparse
import os
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SCRIPT_DIR / "daily-impd.config"
REQUIRED_SETTINGS = (
    "destination",
    "japanese_playlist_id",
    "chinese_playlist_id",
)
OPTIONAL_DEFAULTS = {
    "download_history": ".daily-impd-history.json",
    "openrouter_model": "openrouter/free",
    "yt_dlp_sort": "res:480,vcodec:vp9,acodec:aac,ext:mkv",
}
OPTIONAL_SETTINGS = {
    "openrouter_api_key",
    "OPENROUTER_API_KEY",
    "gemini_api_key",
    "GEMINI_API_KEY",
}
LEGACY_DEFAULTS = {
    "ollama_model": "qwen2.5:7b",
    "ollama_host": "http://localhost:11434",
    "claude_model": "claude-sonnet-5-5",
    "gemini_model": "gemini-3.5-flash-lite",
}
ALL_DEFAULTS = {**OPTIONAL_DEFAULTS, **LEGACY_DEFAULTS}
ALLOWED_SETTINGS = set(REQUIRED_SETTINGS) | set(ALL_DEFAULTS) | OPTIONAL_SETTINGS
PLAYLIST_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def config_path():
    return Path(os.environ.get("IMPD_CONFIG", DEFAULT_CONFIG)).expanduser()


def read_settings(path):
    settings = {}
    try:
        with path.open(encoding="utf-8") as config_file:
            for line_number, raw_line in enumerate(config_file, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    raise ValueError(f"line {line_number} must use key=value format")

                name, value = (part.strip() for part in line.split("=", 1))
                if not name or not value:
                    raise ValueError(
                        f"line {line_number} must have a non-empty key and value"
                    )
                if name in settings:
                    raise ValueError(f"line {line_number} repeats setting {name!r}")
                if name not in ALLOWED_SETTINGS:
                    raise ValueError(f"line {line_number} has unknown setting {name!r}")
                settings[name] = value
    except FileNotFoundError as error:
        raise ValueError(
            f"config file not found: {path}. Copy "
            f"{SCRIPT_DIR / 'daily-impd.config.example'} to {DEFAULT_CONFIG} and edit it."
        ) from error
    except OSError as error:
        raise ValueError(f"cannot read config file {path}: {error}") from error

    missing = [name for name in REQUIRED_SETTINGS if name not in settings]
    if missing:
        raise ValueError(f"missing required setting(s): {', '.join(missing)}")

    destination = settings["destination"]
    if destination.startswith("YOUR_") or destination == "/path/to/active-immersion":
        raise ValueError("destination is still a template; set your media directory")

    for name in ("japanese_playlist_id", "chinese_playlist_id"):
        value = settings[name]
        if not PLAYLIST_ID.fullmatch(value) or value.startswith("YOUR_"):
            raise ValueError(f"{name} must be a playlist ID, not a URL or placeholder")

    for name, default in ALL_DEFAULTS.items():
        settings.setdefault(name, default)

    return settings


def load_config(path=None):
    return read_settings(Path(path or config_path()).expanduser())


def setting_value(settings, name):
    if name not in ALLOWED_SETTINGS:
        raise ValueError(f"unknown setting: {name}")
    return settings[name]


def get_value(settings, name):
    return setting_value(settings, name)


def resolved_path(settings, name, config_file):
    value = Path(setting_value(settings, name)).expanduser()
    if not value.is_absolute():
        value = config_file.resolve().parent / value
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    get_parser = subparsers.add_parser("get", help="print a setting")
    get_parser.add_argument("name")
    path_parser = subparsers.add_parser("path", help="print a resolved path setting")
    path_parser.add_argument("name")
    args = parser.parse_args()

    try:
        path = config_path()
        settings = load_config(path)
        if args.command == "get":
            print(setting_value(settings, args.name))
        else:
            print(resolved_path(settings, args.name, path))
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
