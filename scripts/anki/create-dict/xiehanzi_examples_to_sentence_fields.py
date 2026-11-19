#!/usr/bin/env python3
"""Populate sentence fields and prefer Definitions text after Zhuyin for SimpleMeaning."""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

NOTE_TYPE = "xiehanzi2"
EXAMPLES_FIELD = "Examples"
HANZI_FIELD = "SentHanzi"
ENGLISH_FIELD = "SentEng"
SIMPLE_MEANING_FIELD = "SimpleMeaning"
DEFINITIONS_FIELD = "Definitions"
DEFAULT_ANKI_URL = "http://127.0.0.1:8765"
PREVIEW_COUNT = 100
UPDATE_BATCH_SIZE = 100


class FirstExampleParser(HTMLParser):
    """Extract the Hanzi and translation from the first example-item."""

    TARGET_CLASSES = {
        "example-sim": "hanzi",
        "example-translation": "english",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.example_depth = 0
        self.capture_depth = None
        self.capture_field = None
        self.text = {"hanzi": [], "english": []}
        self.finished = False

    def handle_starttag(self, tag, attrs):
        if self.finished:
            return
        classes = set(dict(attrs).get("class", "").split())
        if self.example_depth == 0:
            if tag == "div" and "example-item" in classes:
                self.example_depth = 1
            return

        if tag == "div":
            self.example_depth += 1
            if self.capture_field is None:
                for class_name, field in self.TARGET_CLASSES.items():
                    if class_name in classes:
                        self.capture_field = field
                        self.capture_depth = self.example_depth
                        break

    def handle_endtag(self, tag):
        if self.finished or tag != "div" or self.example_depth == 0:
            return
        if self.capture_depth == self.example_depth:
            self.capture_field = None
            self.capture_depth = None
        self.example_depth -= 1
        if self.example_depth == 0:
            self.finished = True

    def handle_data(self, data):
        if self.capture_field is not None:
            self.text[self.capture_field].append(data)


def first_example_fields(examples_html):
    parser = FirstExampleParser()
    parser.feed(examples_html)
    if not parser.finished:
        return None

    hanzi = "".join(parser.text["hanzi"]).strip()
    english = "".join(parser.text["english"]).strip()
    if not hanzi:
        return None
    if not english:
        raise ValueError("first example is missing translation")
    return hanzi, english


class DefinitionTextParser(HTMLParser):
    """Extract definition text and locate the end of the Zhuyin container."""

    BLOCK_TAGS = {"br", "div", "li", "ol", "p", "ul"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.div_depth = 0
        self.zhuyin_depth = None
        self.zhuyin_end = None

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK_TAGS:
            self.text.append("\n")
        if tag == "div":
            self.div_depth += 1
            classes = set(dict(attrs).get("class", "").split())
            if self.zhuyin_depth is None and "zhuyin" in classes:
                self.zhuyin_depth = self.div_depth

    def handle_endtag(self, tag):
        if tag == "div" and self.div_depth:
            if self.zhuyin_depth == self.div_depth:
                self.zhuyin_end = len(self.text)
                self.zhuyin_depth = None
            self.div_depth -= 1
        if tag in self.BLOCK_TAGS:
            self.text.append("\n")

    def handle_data(self, data):
        self.text.append(data)


class SimpleMeaningParser(HTMLParser):
    """Extract the text inside the simple-content container."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.div_depth = 0
        self.content_depth = None
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag != "div":
            return
        self.div_depth += 1
        classes = set(dict(attrs).get("class", "").split())
        if self.content_depth is None and "simple-content" in classes:
            self.content_depth = self.div_depth

    def handle_endtag(self, tag):
        if tag != "div" or self.div_depth == 0:
            return
        if self.content_depth == self.div_depth:
            self.content_depth = None
        self.div_depth -= 1

    def handle_data(self, data):
        if self.content_depth is not None:
            self.text.append(data)


def simple_meaning_text(meaning_html):
    parser = SimpleMeaningParser()
    parser.feed(meaning_html)
    if parser.content_depth is None and not parser.text:
        return None
    text = " ".join("".join(parser.text).split())
    return text or None


def definitions_after_zhuyin(definitions_html):
    parser = DefinitionTextParser()
    parser.feed(definitions_html)
    text = "".join(parser.text)
    if parser.zhuyin_end is not None:
        text = "".join(parser.text[parser.zhuyin_end:])
    else:
        zhuyin = re.search(
            r"[\u3105-\u312f\u31a0-\u31bf]+[ˉˊˇˋ˙・]*",
            text,
        )
        if zhuyin is None:
            return None
        text = text[zhuyin.end():]

    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "<br>".join(line for line in lines if line) or None


def invoke(url, action, **params):
    request = urllib.request.Request(
        url,
        json.dumps({"action": action, "version": 6, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"AnkiConnect {action} failed with HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach AnkiConnect at {url}: {error}") from error

    if result.get("error"):
        raise RuntimeError(f"AnkiConnect {action}: {result['error']}")
    return result["result"]


def prepare_updates(anki_url):
    model_names = invoke(anki_url, "modelNames")
    if NOTE_TYPE not in model_names:
        raise RuntimeError(f'Anki note type "{NOTE_TYPE}" was not found')

    note_ids = invoke(anki_url, "findNotes", query=f'note:"{NOTE_TYPE}"')
    notes = invoke(anki_url, "notesInfo", notes=note_ids) if note_ids else []
    updates = []
    unchanged = 0
    skipped_blank = 0

    for note in notes:
        if note.get("modelName") != NOTE_TYPE:
            continue
        fields = note["fields"]
        missing = {
            EXAMPLES_FIELD, HANZI_FIELD, ENGLISH_FIELD, SIMPLE_MEANING_FIELD,
            DEFINITIONS_FIELD,
        } - fields.keys()
        if missing:
            raise RuntimeError(
                f"Note {note['noteId']} is missing required field(s): "
                f"{', '.join(sorted(missing))}; no notes were changed"
            )

        try:
            example = first_example_fields(fields[EXAMPLES_FIELD]["value"])
        except ValueError as error:
            raise RuntimeError(
                f"Could not read the first example on note {note['noteId']}: "
                f"{error}; no notes were changed"
            ) from error
        fields_to_update = {}
        if example is None:
            skipped_blank += 1
        else:
            hanzi, english = example
            if fields[HANZI_FIELD]["value"] != hanzi:
                fields_to_update[HANZI_FIELD] = hanzi
            if fields[ENGLISH_FIELD]["value"] != english:
                fields_to_update[ENGLISH_FIELD] = english

        simple_meaning = definitions_after_zhuyin(
            fields[DEFINITIONS_FIELD]["value"]
        )
        if simple_meaning is None:
            simple_meaning = simple_meaning_text(
                fields[SIMPLE_MEANING_FIELD]["value"]
            )
        if (simple_meaning is not None
                and fields[SIMPLE_MEANING_FIELD]["value"] != simple_meaning):
            fields_to_update[SIMPLE_MEANING_FIELD] = simple_meaning

        if fields_to_update:
            updates.append({"id": note["noteId"], "fields": fields_to_update})
        elif example is not None:
            unchanged += 1

    return len(notes), updates, unchanged, skipped_blank


def update_notes(anki_url, updates):
    if not updates:
        return

    print(f"Updating notes: 0/{len(updates)} (0%)", flush=True)
    for start in range(0, len(updates), UPDATE_BATCH_SIZE):
        batch = updates[start:start + UPDATE_BATCH_SIZE]
        actions = [
            {
                "action": "updateNoteFields",
                "params": {
                    "note": {
                        "id": update["id"],
                        "fields": update["fields"],
                    }
                },
            }
            for update in batch
        ]
        try:
            results = invoke(anki_url, "multi", actions=actions)
            if not isinstance(results, list) or len(results) != len(batch):
                raise RuntimeError(
                    f"AnkiConnect returned an unexpected result for a "
                    f"{len(batch)}-note batch"
                )
            for result in results:
                if isinstance(result, dict) and result.get("error"):
                    raise RuntimeError(
                        f"AnkiConnect updateNoteFields: {result['error']}"
                    )
        except RuntimeError as error:
            raise RuntimeError(
                f"Stopped after submitting {start} of {len(updates)} notes; "
                f"the current batch may have partially applied: {error}"
            ) from error
        completed = start + len(batch)
        progress = completed / len(updates)
        print(
            f"Updating notes: {completed}/{len(updates)} ({progress:.0%})",
            flush=True,
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

    total, updates, unchanged, skipped_blank = prepare_updates(args.anki_url)
    print(
        f'Found {total} note(s) of type "{NOTE_TYPE}": '
        f"{len(updates)} to update, {unchanged} already current, "
        f"{skipped_blank} without a first example sentence."
    )
    for update in updates[:PREVIEW_COUNT]:
        print(f"  {update['id']}:")
        for field, value in update["fields"].items():
            print(f"    {field}: {value}")
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
