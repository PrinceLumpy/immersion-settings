"""Extend subtitle cue display times while avoiding overlap."""
import argparse
import os
import re
import tempfile
from pathlib import Path

PAD_SECONDS = 0.5
TIMESTAMP = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$"
)


def parse_timestamp(value):
    match = TIMESTAMP.fullmatch(value)
    if not match:
        raise ValueError(f"invalid SRT timestamp: {value!r}")
    hours, minutes, seconds, milliseconds = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def format_timestamp(value):
    milliseconds = round(max(value, 0) * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def read_cues(path):
    content = path.read_text(encoding="utf-8-sig").strip()
    if not content:
        raise ValueError(f"subtitle file is empty: {path}")

    cues = []
    for cue_number, block in enumerate(re.split(r"\r?\n\s*\r?\n", content), 1):
        lines = block.splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            raise ValueError(f"invalid SRT cue {cue_number} in {path}")
        start, end = lines[1].split(" --> ", 1)
        start_time = parse_timestamp(start)
        end_time = parse_timestamp(end)
        if end_time < start_time:
            raise ValueError(f"SRT cue {cue_number} ends before it starts in {path}")
        text = "\n".join(lines[2:])
        if not text.strip():
            raise ValueError(f"SRT cue {cue_number} has no text in {path}")
        cues.append([start_time, end_time, text])
    return cues


def pad_cues(cues):
    for cue in cues:
        cue[0] = max(cue[0] - PAD_SECONDS, 0)
        cue[1] += PAD_SECONDS

    for current, following in zip(cues, cues[1:]):
        if current[1] > following[0]:
            midpoint = (current[1] + following[0]) / 2
            current[1] = midpoint
            following[0] = midpoint


def write_cues(path, cues):
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            for index, (start, end, text) in enumerate(cues, 1):
                output.write(
                    f"{index}\n{format_timestamp(start)} --> "
                    f"{format_timestamp(end)}\n{text}\n\n"
                )
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    cues = read_cues(args.source)
    pad_cues(cues)
    write_cues(args.destination, cues)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(f"Subtitle padding failed: {error}") from error
