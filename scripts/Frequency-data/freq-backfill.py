import json, re, urllib.request
import jieba

DECK = "Mandarin Core 5K: Frequency-Ordered Sentence Cards"   # None = all decks
FREQ_FILE = "SUBTLEX-CH-WF"
WORD_COL, COUNT_COL = 0, 1  # Word, WCount
MISSING = 999999

def invoke(action, **params):
    req = urllib.request.Request(
        "http://localhost:8765",
        json.dumps({"action": action, "version": 6, "params": params}).encode(),
    )
    res = json.load(urllib.request.urlopen(req))
    if res["error"]:
        raise Exception(res["error"])
    return res["result"]

rows = []
with open(FREQ_FILE, encoding="utf-8") as f:
    for line in f:
        p = line.rstrip("\r\n").split("\t")
        try:
            rows.append((p[WORD_COL], float(p[COUNT_COL])))
        except (IndexError, ValueError):
            pass
rows.sort(key=lambda r: -r[1])
rank = {}
for i, (w, _) in enumerate(rows, 1):
    rank.setdefault(w, i)

tags = re.compile(r"<[^>]+>")
han = re.compile(r"[\u4e00-\u9fff]")
ids = invoke("findNotes", query=f'"deck:{DECK}"' if DECK else "*")
actions, missing = [], []

for note in invoke("notesInfo", notes=ids):
    f = note["fields"]
    if "VocabHanzi" not in f or "Freq" not in f:
        continue

    current = tags.sub("", f["Freq"]["value"]).strip()
    if current not in ("", str(MISSING)):
        continue  # already has a real value

    word = tags.sub("", f["VocabHanzi"]["value"]).strip()
    r = rank.get(word)
    if r is None:
        parts = [p for p in jieba.lcut(word) if han.search(p)]
        rs = [rank.get(p) for p in parts]
        if parts and all(rs):
            r = max(rs)  # rarest component decides
        else:
            missing.append(word)
            r = MISSING

    if str(r) == current:
        continue  # nothing to change
    actions.append({"action": "updateNoteFields", "params": {
        "note": {"id": note["noteId"], "fields": {"Freq": str(r)}}}})

for i in range(0, len(actions), 500):
    invoke("multi", actions=actions[i:i + 500])

print(f"Updated {len(actions)} notes, still missing {len(missing)}: {missing}")