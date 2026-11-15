# Thoughts on auto sentence mining

Sentence mining is most useful when it captures something that was genuinely
hard to understand in context. That includes unfamiliar vocabulary, but also
sentences made up of words you already know in a structure you have not seen
before.

If you are watching the video anyway, mining as you watch can be more useful
than automating it. 


Automatic sentence mining has limits. It cannot distinguish different uses
of the same words.
It only pays attention to words, so it will miss structurally unfamiliar
sentences of words that you already know.
Its segmentation may also disagree with Yomitan's dictionary. For
example, jieba may treat `一键` as one word while Yomitan looks up the
characters separately, making automatic backfill unreliable.

Automation can still help on days when you are tired or do not enjoy the
content, when manual mining feels like too much effort. It is probably best
treated as an optional fallback or source of candidates, rather than a
replacement for mining while watching. The goal is to reduce effort without
losing the learner's judgment about which sentences are worth studying.
