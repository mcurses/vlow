"""Post-hoc known-words correction for backends that cannot be prompted.

Whisper takes an initial_prompt and AssemblyAI takes keyterms, so their
output is biased *during* decoding. Parakeet has no such hook, so the
transcript is corrected afterwards: any run of tokens that is a close
spelling match for a configured known word is replaced by that word. This
is the same trade-off Handy makes with its fuzzy fallback — conservative on
purpose, because a false correction is worse than a missed one.
"""

import difflib
import re

_MIN_CHARS = 3  # never fuzzy-match very short terms ("AI", "EU")
_THRESHOLD = 0.8  # SequenceMatcher ratio on the lowercased strings

_LEAD = re.compile(r"^[^\w]+", re.UNICODE)
_TRAIL = re.compile(r"[^\w]+$", re.UNICODE)


def _core(token: str) -> str:
    return _TRAIL.sub("", _LEAD.sub("", token))


def apply_known_words(text: str, words: list[str], threshold: float = _THRESHOLD) -> str:
    """Return `text` with near-misses of `words` replaced by the exact spelling.

    Multi-word terms are matched as a sliding window of the same length;
    longer terms are tried first so "EMMA Studio" wins over "EMMA".
    Surrounding punctuation on the matched window is preserved."""
    if not text or not words:
        return text
    tokens = text.split()
    if not tokens:
        return text
    for word in sorted((w for w in words if w.strip()), key=lambda w: -len(w.split())):
        parts = word.split()
        n = len(parts)
        target = word.lower()
        if len(_core(word)) < _MIN_CHARS or n == 0:
            continue
        i = 0
        while i + n <= len(tokens):
            window = tokens[i : i + n]
            cand = " ".join(_core(t) for t in window)
            if not cand:
                i += 1
                continue
            cand_l = cand.lower()
            if cand_l == target:
                hit = cand != word  # fix casing only
            else:
                hit = (
                    len(cand_l) >= _MIN_CHARS
                    and difflib.SequenceMatcher(None, cand_l, target).ratio() >= threshold
                )
            if hit:
                lead = _LEAD.match(window[0])
                trail = _TRAIL.search(window[-1])
                tokens[i : i + n] = [
                    (lead.group(0) if lead else "") + word + (trail.group(0) if trail else "")
                ]
            i += 1
    return " ".join(tokens)
