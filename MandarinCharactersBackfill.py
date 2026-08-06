#!/usr/bin/env python3
"""
Find characters that appear in Mandarin::TSC (field VocabHanzi) but are not
yet present in Mandarin::Characters (field Character).

Incremental: only re-scans TSC cards added since the last run (tracked in
a small JSON state file), so repeat runs stay fast.
"""

import json
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

ANKI_CONNECT_URL = "http://127.0.0.1:8765"
OUTPUT_FILE = Path("missing_chars.txt")
CHAR_DECK = "Mandarin::Characters"
CHAR_FIELD = "Character"
TSC_DECK = "Mandarin::TSC"
VOCAB_FIELD = "VocabHanzi"

HANZI_RE = re.compile(r"[\u4e00-\u9fff]")

# Edit this manually after you've added the missing characters via Yomitan.
# Set to None to scan the entire TSC deck.
LAST_RUN_DATE = "2026-08-06"  # format: YYYY-MM-DD


def invoke(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(ANKI_CONNECT_URL, payload)
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    if result.get("error"):
        raise RuntimeError(f"AnkiConnect error on {action}: {result['error']}")
    return result["result"]


def get_field_values(deck, field):
    note_ids = invoke("findNotes", query=f'deck:"{deck}"')
    if not note_ids:
        return []
    infos = invoke("notesInfo", notes=note_ids)
    return [n["fields"][field]["value"] for n in infos if field in n["fields"]]


def days_since(iso_date_str):
    d = datetime.strptime(iso_date_str, "%Y-%m-%d").date()
    return max((date.today() - d).days, 0)


def main():
    # Full character set — needed each run to compare against.
    char_values = get_field_values(CHAR_DECK, CHAR_FIELD)
    known_chars = set()
    for v in char_values:
        known_chars.update(HANZI_RE.findall(v))
    print(f"Loaded {len(known_chars)} known characters from {CHAR_DECK}")

    # TSC query — incremental if LAST_RUN_DATE is set, full scan otherwise.
    if LAST_RUN_DATE:
        n = days_since(LAST_RUN_DATE)
        query = f'deck:"{TSC_DECK}" added:{n}'
        print(f"Scanning {TSC_DECK} cards added in the last {n} day(s) "
              f"(since {LAST_RUN_DATE})")
    else:
        query = f'deck:"{TSC_DECK}"'
        print(f"LAST_RUN_DATE is None — scanning all of {TSC_DECK}")

    note_ids = invoke("findNotes", query=query)
    infos = invoke("notesInfo", notes=note_ids) if note_ids else []

    missing = set()
    for n in infos:
        text = n["fields"].get(VOCAB_FIELD, {}).get("value", "")
        for ch in HANZI_RE.findall(text):
            if ch not in known_chars:
                missing.add(ch)

    print(f"Scanned {len(infos)} TSC card(s)")
    if missing:
        OUTPUT_FILE.write_text("\n".join(sorted(missing)) + "\n")
        print(f"\n{len(missing)} character(s) missing from Characters "
              f"-> written to {OUTPUT_FILE}")
    else:
        print("\nNo missing characters found.")

    print(f"\nLAST_RUN_DATE is still {LAST_RUN_DATE!r} — update it manually "
          "in the script once you've added these characters via Yomitan.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)