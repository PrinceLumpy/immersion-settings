#!/usr/bin/env python3
"""Copy processed Xiexie meanings to matching xiehanzi2 notes."""

import argparse
import sys
from html.parser import HTMLParser

from xiehanzi_examples_to_sentence_fields import (
    DEFAULT_ANKI_URL,
    DEFINITIONS_FIELD,
    SIMPLE_MEANING_FIELD,
    definitions_after_zhuyin,
    invoke,
    simple_meaning_text,
    update_notes,
)

SOURCE_NOTE_TYPE = "xiexie"
TARGET_NOTE_TYPE = "Mandarin-HSK-TSC"
SOURCE_KEY_FIELD = "Simplified"
TARGET_KEY_FIELD = "VocabHanzi"
PREVIEW_COUNT = 20


class PlainTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []

    def handle_data(self, data):
        self.text.append(data)


def normalized_key(value):
    parser = PlainTextParser()
    parser.feed(value)
    return "".join("".join(parser.text).split())


def processed_meaning(fields):
    common_meaning = simple_meaning_text(
        fields[SIMPLE_MEANING_FIELD]["value"]
    )
    definitions = definitions_after_zhuyin(fields[DEFINITIONS_FIELD]["value"])
    return "<br>".join(
        part for part in (common_meaning, definitions) if part
    ) or None


def require_fields(note, field_names):
    missing = field_names - note["fields"].keys()
    if missing:
        raise RuntimeError(
            f'Note {note["noteId"]} of type "{note["modelName"]}" is missing '
            f"required field(s): {', '.join(sorted(missing))}; "
            "no notes were changed"
        )


def prepare_updates(anki_url):
    model_names = invoke(anki_url, "modelNames")
    for model_name in (SOURCE_NOTE_TYPE, TARGET_NOTE_TYPE):
        if model_name not in model_names:
            raise RuntimeError(f'Anki note type "{model_name}" was not found')

    source_ids = invoke(
        anki_url, "findNotes", query=f'note:"{SOURCE_NOTE_TYPE}"'
    )
    target_ids = invoke(
        anki_url, "findNotes", query=f'note:"{TARGET_NOTE_TYPE}"'
    )
    source_notes = (
        invoke(anki_url, "notesInfo", notes=source_ids) if source_ids else []
    )
    target_notes = (
        invoke(anki_url, "notesInfo", notes=target_ids) if target_ids else []
    )

    source_meanings = {}
    skipped_sources = 0
    for note in source_notes:
        if note.get("modelName") != SOURCE_NOTE_TYPE:
            continue
        require_fields(
            note,
            {SOURCE_KEY_FIELD, SIMPLE_MEANING_FIELD, DEFINITIONS_FIELD},
        )
        key = normalized_key(note["fields"][SOURCE_KEY_FIELD]["value"])
        meaning = processed_meaning(note["fields"])
        if not key or not meaning:
            skipped_sources += 1
            continue
        previous = source_meanings.get(key)
        if previous is not None and previous[0] != meaning:
            raise RuntimeError(
                f'Source notes {previous[1]} and {note["noteId"]} have '
                f'different meanings for "{key}"; no notes were changed'
            )
        source_meanings[key] = (meaning, note["noteId"])

    updates = []
    matched_targets = 0
    unmatched_targets = 0
    unchanged = 0
    for note in target_notes:
        if note.get("modelName") != TARGET_NOTE_TYPE:
            continue
        require_fields(note, {TARGET_KEY_FIELD, SIMPLE_MEANING_FIELD})
        key = normalized_key(note["fields"][TARGET_KEY_FIELD]["value"])
        source = source_meanings.get(key)
        if not key or source is None:
            unmatched_targets += 1
            continue
        matched_targets += 1
        meaning = source[0]
        if note["fields"][SIMPLE_MEANING_FIELD]["value"] == meaning:
            unchanged += 1
            continue
        updates.append(
            {
                "id": note["noteId"],
                "fields": {SIMPLE_MEANING_FIELD: meaning},
            }
        )

    return (
        len(source_notes),
        len(target_notes),
        updates,
        matched_targets,
        unmatched_targets,
        unchanged,
        skipped_sources,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--anki-url",
        default=DEFAULT_ANKI_URL,
        help=f"AnkiConnect URL (default: {DEFAULT_ANKI_URL})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the fields; without this option, only preview changes",
    )
    args = parser.parse_args()

    (
        source_count,
        target_count,
        updates,
        matched_targets,
        unmatched_targets,
        unchanged,
        skipped_sources,
    ) = prepare_updates(args.anki_url)
    print(
        f'Found {source_count} "{SOURCE_NOTE_TYPE}" source note(s) and '
        f'{target_count} "{TARGET_NOTE_TYPE}" destination note(s): '
        f"{matched_targets} matched, {len(updates)} to update, "
        f"{unchanged} already current, {unmatched_targets} without a match, "
        f"{skipped_sources} source note(s) missing a key or usable meaning."
    )
    for update in updates[:PREVIEW_COUNT]:
        print(f"  {update['id']}:")
        print(
            f"    {SIMPLE_MEANING_FIELD}: "
            f"{update['fields'][SIMPLE_MEANING_FIELD]}"
        )
    if len(updates) > PREVIEW_COUNT:
        print(f"  ... and {len(updates) - PREVIEW_COUNT} more")

    if not args.apply:
        print("Preview only; rerun with --apply to write the displayed fields.")
        return

    update_notes(args.anki_url, updates)
    print(f"Updated {len(updates)} note(s).")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        sys.exit(f"Failed: {error}")
