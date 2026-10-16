import json, re, urllib.request

DECK = "Mandarin 10K: Targeted Sentence Cards"   # None = all decks
FREQ_FILE = "SUBTLEX-CH-WF"
TOP_N = 10000          # check the top N SUBTLEX words
OUT_FILE = "missing_words.txt"

def invoke(action, **params):
    req = urllib.request.Request(
        "http://localhost:8765",
        json.dumps({"action": action, "version": 6, "params": params}).encode(),
    )
    res = json.load(urllib.request.urlopen(req))
    if res["error"]:
        raise Exception(res["error"])
    return res["result"]

tags = re.compile(r"<[^>]+>")
han = re.compile(r"^[\u4e00-\u9fff]+$")

def norm(s):
    s = tags.sub("", s).replace("&nbsp;", "")
    s = re.sub(r"[(（][^)）]*[)）]", "", s)   # 每(个) -> 每
    return s.strip().lstrip("\ufeff")

# Words already in the deck
ids = invoke("findNotes", query=f'"deck:{DECK}"' if DECK else "*")
have = set()
for n in invoke("notesInfo", notes=ids):
    f = n["fields"]
    if "VocabHanzi" in f:
        have.add(norm(f["VocabHanzi"]["value"]))

# Ranked SUBTLEX list (Chinese-only entries; skips names/punctuation/Latin)
rows = []
with open(FREQ_FILE, encoding="utf-8") as fh:
    for line in fh:
        p = line.rstrip("\r\n").split("\t")
        try:
            w, c = p[0], float(p[1])
        except (IndexError, ValueError):
            continue
        if han.match(w):
            rows.append((w, c))
rows.sort(key=lambda r: -r[1])

missing = []
for rank, (w, c) in enumerate(rows[:TOP_N], 1):
    if w not in have:
        missing.append((rank, w, int(c)))

with open(OUT_FILE, "w", encoding="utf-8") as out:
    for rank, w, c in missing:
        out.write(f"{rank}\t{w}\t{c}\n")

print(f"{len(missing)} of the top {TOP_N} words are not in the deck:")
for rank, w, c in missing[:50]:
    print(rank, w)
print(f"\nFull list saved to {OUT_FILE}")