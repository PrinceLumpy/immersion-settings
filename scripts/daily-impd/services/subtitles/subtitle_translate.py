#!/usr/bin/env python3
"""Translate SRT cues with a local Ollama model while preserving cue timings."""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import load_config, get_value

BATCH_SIZE = 25
TIMESTAMP = re.compile(
    r"^\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})(?:\s+.*)?$"
)


def read_srt(path):
    content = path.read_text(encoding="utf-8-sig").strip()
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", content):
        lines = block.splitlines()
        timing_index = next(
            (index for index, line in enumerate(lines) if TIMESTAMP.match(line)),
            None,
        )
        if timing_index is None:
            raise ValueError(f"Invalid SRT cue in {path}: missing timestamp")
        match = TIMESTAMP.match(lines[timing_index])
        text = "\n".join(lines[timing_index + 1 :]).strip()
        if not text:
            raise ValueError(f"Invalid SRT cue in {path}: empty subtitle text")
        cues.append((match.group(1).replace(".", ","), match.group(2).replace(".", ","), text))
    if not cues:
        raise ValueError(f"No subtitle cues found in {path}")
    return cues


def translate_batch(cues, first_index, model, host):
    items = [
        {"index": first_index + offset, "text": text}
        for offset, (_, _, text) in enumerate(cues)
    ]
    prompt = (
        "Identify the source language and translate these subtitle cues into "
        "natural English. Keep each translation concise and faithful. Return "
        "only a JSON object "
        'with a "translations" array containing one object per input, each with '
        '"index" and "text" fields. Keep every index unchanged.\n'
        f"Input: {json.dumps(items, ensure_ascii=False)}"
    )
    request_data = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=request_data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach Ollama at {host}: {error}") from error
    try:
        payload = json.loads(result["message"]["content"])
        translated = {
            item["index"]: item["text"] for item in payload["translations"]
        }
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("Ollama returned an invalid subtitle translation response") from error
    expected = {item["index"] for item in items}
    if set(translated) != expected or any(
        not isinstance(text, str) or not text.strip()
        for text in translated.values()
    ):
        raise RuntimeError("Ollama did not return exactly one non-empty translation per cue")
    return [translated[item["index"]] for item in items]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("english", type=Path)
    args = parser.parse_args()
    source = args.source
    target = args.english
    if source.resolve() == target.resolve():
        raise SystemExit("Source and English subtitle paths must be different")

    cues = read_srt(source)
    config = load_config()
    model = get_value(config, "ollama_model")
    host = get_value(config, "ollama_host")
    translations = []
    for start in range(0, len(cues), BATCH_SIZE):
        batch = cues[start : start + BATCH_SIZE]
        translations.extend(
            translate_batch(batch, start + 1, model, host)
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as output:
        for index, ((start, end, _), text) in enumerate(
            zip(cues, translations), start=1
        ):
            output.write(f"{index}\n{start} --> {end}\n{text}\n\n")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Subtitle translation failed: {error}") from error
