#!/usr/bin/env python3
"""
Read a subs2srs TSV, find words you don't know yet, and create new notes:

    VocabHanzi: 取决于
    SentHanzi:  这<b>取决于</b>我们的母语和我们所知道的语言
    SentAudio:  [sound:xxx.mp3]   (referenced by the TSV; imported into Anki)
    SentEng:    It depends on our native language and the languages we know

Setup:  pip install jieba
        Set cedict_path in auto-mine-zh.config.json to your CC-CEDICT text file.
        Audio defaults to the matching .media folder beside the TSV.
        Anki open with the AnkiConnect add-on (code 2055492159)
        Settings: auto-mine-zh.config.json next to this script
        Audio referenced by the TSV is imported into Anki on non-dry runs.

Example:
  python auto-mine-zh.py episode.tsv --dry-run
Drop --dry-run to actually create the notes.
"""
import argparse
import base64
import csv
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

import jieba.posseg as pseg

CONFIG_PATH = Path(__file__).with_name("auto-mine-zh.config.json")
CEDICT_ENTRY = re.compile(r"^(\S+)\s+(\S+)\s+\[")
SKIP_FLAGS = {"x", "w", "u", "p", "c", "r", "m", "q", "y", "e", "o", "h", "k",
              "eng", "nr", "ns", "nt", "nz", "t", "zg", "uj", "ul", "uz", "ud"}
HAS_HANZI = re.compile(r"[一-鿿]")
TAG = re.compile(r"<[^>]+>")
SOUND = re.compile(r"\[sound:([^\]]+)\]")


def load_cedict(path):
    """Load CC-CEDICT traditional and simplified headwords for validation."""
    words = set()
    with path.open(encoding="utf-8-sig") as f:
        for line in f:
            match = CEDICT_ENTRY.match(line)
            if match:
                words.update(match.groups())

    if not words:
        raise ValueError(f"No CC-CEDICT entries found in {path}")

    return words


def split_to_cedict_words(token, dictionary_words):
    """Split an unknown token to maximize the characters covered by dictionary words."""
    best = [(0, 0, []) for _ in range(len(token) + 1)]
    for start in range(len(token) - 1, -1, -1):
        suffix_score, suffix_count, suffix_parts = best[start + 1]
        best[start] = (
            suffix_score,
            suffix_count,
            [(token[start], False), *suffix_parts],
        )
        for end in range(len(token), start, -1):
            word = token[start:end]
            if word not in dictionary_words:
                continue
            suffix_score, suffix_count, suffix_parts = best[end]
            score = (suffix_score + len(word), suffix_count - 1)
            if score > best[start][:2]:
                best[start] = (
                    *score,
                    [(word, True), *suffix_parts],
                )
    return best[0][2]


def load_config():
    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)

    required = {
        "anki_connect_url", "deck_name", "note_type", "fields", "tags",
        "min_word_length", "dry_run_preview_count",
    }
    missing = required - config.keys()
    if missing:
        raise ValueError(f"{CONFIG_PATH} is missing settings: {', '.join(sorted(missing))}")

    required_fields = {"vocab", "sentence", "audio", "english"}
    missing_fields = required_fields - config["fields"].keys()
    if missing_fields:
        raise ValueError(
            f"{CONFIG_PATH} fields is missing: {', '.join(sorted(missing_fields))}")
    return config


def audio_source_dir(config, tsv_path):
    source_dir = config.get("audio_source_dir")
    if source_dir is None:
        tsv_path = Path(tsv_path).resolve()
        parent = tsv_path.parent
        media_dirs = [
            path for path in parent.iterdir()
            if path.is_dir() and path.name.endswith(".media")
        ]
        matching = [
            path for path in media_dirs
            if (tsv_path.stem == path.stem
                or tsv_path.stem.startswith((path.stem + "_", path.stem + "-", path.stem + " ")))
        ]
        if matching:
            return max(matching, key=lambda path: len(path.name))
        if len(media_dirs) == 1:
            return media_dirs[0]
        if len(media_dirs) > 1:
            names = ", ".join(path.name for path in media_dirs)
            raise ValueError(
                f"Could not match {tsv_path.name} to a .media folder in {parent}; "
                f"set audio_source_dir in {CONFIG_PATH}. Found: {names}")
        return parent
    path = Path(source_dir).expanduser()
    return path if path.is_absolute() else CONFIG_PATH.parent / path


def check_audio_files(notes, audio_field, source_dir):
    for note in notes:
        for match in SOUND.finditer(note["fields"][audio_field]):
            filename = match.group(1)
            if Path(filename).name != filename:
                raise ValueError(f"Audio reference must be a filename, got: {filename}")
            path = source_dir / filename
            if not path.is_file():
                raise FileNotFoundError(f"Audio referenced by TSV not found: {path}")


def import_audio(notes, audio_field, source_dir, anki_url):
    imported = {}
    for note in notes:
        audio = note["fields"][audio_field]

        def store(match):
            filename = match.group(1)
            if Path(filename).name != filename:
                raise ValueError(f"Audio reference must be a filename, got: {filename}")
            if filename not in imported:
                path = source_dir / filename
                if not path.is_file():
                    raise FileNotFoundError(f"Audio referenced by TSV not found: {path}")
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                stored_name = invoke(
                    anki_url, "storeMediaFile", filename=filename, data=data)
                if not isinstance(stored_name, str) or not stored_name:
                    raise RuntimeError(f"AnkiConnect did not store media file: {filename}")
                imported[filename] = stored_name
            return f"[sound:{imported[filename]}]"

        note["fields"][audio_field] = SOUND.sub(store, audio)


def invoke(url, action, **params):
    req = urllib.request.Request(
        url, json.dumps({"action": action, "version": 6, "params": params}).encode())
    resp = json.load(urllib.request.urlopen(req))
    if resp.get("error"):
        raise RuntimeError(f"AnkiConnect {action}: {resp['error']}")
    return resp["result"]


def clean(text):
    return TAG.sub("", SOUND.sub("", text)).replace("&nbsp;", " ").strip()


def process_sentence(sentence, min_len, dictionary_words):
    """Return dictionary-backed candidates, first occurrence of each word only."""
    segs = []
    for item in pseg.cut(sentence, HMM=False):
        word, flag = item.word, item.flag
        if word in dictionary_words:
            segs.append((word, flag))
            continue
        segs.extend(
            (part, "x" if is_dictionary_word else "")
            for part, is_dictionary_word in split_to_cedict_words(word, dictionary_words)
        )

    found = {}
    for i, (word, flag) in enumerate(segs):
        if (word in found or word not in dictionary_words
                or (flag in SKIP_FLAGS and flag != "x") or flag[:1] == "w"):
            continue
        if len(word) < min_len or not HAS_HANZI.search(word):
            continue
        parts = [w for w, _ in segs]
        parts[i] = f"<b>{word}</b>"
        found[word] = "".join(parts)
    return found


def read_tsv(path):
    """Read a subs2srs TSV -> [(sentence, audio, English subtitle)]."""
    with open(path, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.reader(f, delimiter="\t") if r]
    counts = defaultdict(int)
    for r in rows[:200]:
        for i, c in enumerate(r):
            if SOUND.search(c):
                counts[i] += 1
    audio_col = max(counts, key=counts.get) if counts else -1

    hanzi = defaultdict(int)
    for r in rows[:200]:
        for i, c in enumerate(r):
            if i != audio_col:
                hanzi[i] += len(HAS_HANZI.findall(clean(c)))
    sent_col = max(hanzi, key=hanzi.get) if hanzi else -1

    latin = defaultdict(int)
    for r in rows[:200]:
        for i, c in enumerate(r):
            if i not in {sent_col, audio_col}:
                text = clean(c)
                if not HAS_HANZI.search(text):
                    latin[i] += sum(ch.isascii() and ch.isalpha() for ch in text)
    eng_col = max(latin, key=latin.get) if latin and max(latin.values()) else -1

    print(f"TSV columns: sentence={sent_col}, audio={audio_col}, "
          f"English={eng_col} (0-based)")
    out = []
    for r in rows:
        sent = clean(r[sent_col]) if len(r) > sent_col else ""
        audio = r[audio_col].strip() if 0 <= audio_col < len(r) else ""
        eng = clean(r[eng_col]) if 0 <= eng_col < len(r) and eng_col != sent_col else ""
        if sent:
            out.append((sent, audio, eng))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", help="subs2srs TSV file")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cedict", help="CC-CEDICT text file (overrides cedict_path in config)")
    args = ap.parse_args()
    config = load_config()
    fields = config["fields"]
    anki_url = config["anki_connect_url"]

    cedict_path = args.cedict or config.get("cedict_path")
    if not cedict_path:
        raise ValueError("Set cedict_path in the config or pass --cedict")
    cedict_path = Path(cedict_path).expanduser()
    if not cedict_path.is_absolute():
        cedict_path = CONFIG_PATH.parent / cedict_path
    dictionary_words = load_cedict(cedict_path)
    print(f"{len(dictionary_words)} CC-CEDICT headwords loaded from {cedict_path}")

    # Words you already have
    known = set()
    ids = invoke(
        anki_url, "findNotes", query=f'deck:"{config["deck_name"]}"')
    for info in invoke(anki_url, "notesInfo", notes=ids) if ids else []:
        f = info["fields"].get(fields["vocab"])
        if f:
            known.add(clean(f["value"]))
    print(f"{len(known)} known words in '{config['deck_name']}'")

    source = read_tsv(args.tsv)
    print(f"{len(source)} sentences in '{args.tsv}'")

    # word -> [(plain_len, bolded, audio, English subtitle)]
    cands = defaultdict(list)
    for sent, audio, eng in source:
        sentence_words = process_sentence(sent, config["min_word_length"], dictionary_words)
        for word, bolded in sentence_words.items():
            if word not in known:
                cands[word].append((len(sent), bolded, audio, eng))

    # most frequent words first; shortest sentence per word
    ranked = sorted(cands, key=lambda w: -len(cands[w]))

    notes = []
    for word in ranked:
        _, bolded, audio, eng = min(cands[word])
        notes.append({
            "deckName": config["deck_name"],
            "modelName": config["note_type"],
            "fields": {fields["vocab"]: word,
                       fields["sentence"]: bolded,
                       fields["audio"]: audio,
                       fields["english"]: eng},
            "options": {"allowDuplicate": False},
            "tags": config["tags"],
        })

    audio_dir = audio_source_dir(config, args.tsv)
    check_audio_files(notes, fields["audio"], audio_dir)
    if args.dry_run:
        for n in notes[:config["dry_run_preview_count"]]:
            f = n["fields"]
            print(f"{f[fields['vocab']]}\t{f[fields['sentence']]}\t"
                  f"{f[fields['audio']]}\t{f[fields['english']]}")
        print(f"[dry run] {len(notes)} notes would be created")
        return

    import_audio(notes, fields["audio"], audio_dir, anki_url)
    results = invoke(anki_url, "addNotes", notes=notes)
    ok = sum(r is not None for r in results)
    print(f"created {ok} notes, skipped {len(results) - ok} (duplicates/errors)")


if __name__ == "__main__":
    main()
