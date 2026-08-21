"""
Deterministic checks for persona voice rules.

Anything decidable by inspecting the text belongs here rather than in a prompt: it is
cheaper, it cannot drift between runs, and it does not consume a revision round-trip.
Every rule here exists because a live run violated it.
"""

import re
from typing import List, Tuple

# Shortest run of shared words treated as copying rather than coincidence. Five is long
# enough that ordinary phrasing ("it is worth noting that") does not trip it.
MIN_BORROWED_RUN_WORDS = 5

# Naming a structural beat, or addressing the writing instructions themselves, is
# scaffolding. A model handed a numbered structure will otherwise emit the beat names
# as headings, and one draft repeated the plain-language instruction back as prose.
SCAFFOLDING_PATTERNS = [
    re.compile(r"\bthe obvious (?:claim|assumption)\b", re.I),
    re.compile(r"\bthe turn is\b", re.I),
    re.compile(r"\bthe takeaway line\b", re.I),
    re.compile(r"\ba smart (?:reader|adult|casual reader)\b", re.I),
    re.compile(r"\bwith no background in this\b", re.I),
    re.compile(r"\bin plain (?:language|english)\b", re.I),
    re.compile(r"\bcasual reader would assume\b", re.I),
]

# Endings the persona does not use: the post stops when the mechanism is explained.
CLOSING_TAKEAWAY_PATTERNS = [
    re.compile(r"\b(?:the\s+)?(?:key\s+)?takeaway\b", re.I),
    re.compile(r"^\s*in short[,:]", re.I | re.M),
    re.compile(r"^\s*(?:the\s+)?bottom line[,:]", re.I | re.M),
    re.compile(r"\bthis shows that\b", re.I),
    re.compile(r"\bwhat this means (?:is|for)\b", re.I),
    re.compile(r"\bthe future of ai\b", re.I),
]

# A definition in brackets is a gloss, not a translation. The term should be rewritten.
PARENTHETICAL_DEFINITION = re.compile(r"\(([^)]{25,})\)")

EM_DASH_CHARS = ("\u2014", "\u2013", "--")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def em_dashes(text: str) -> bool:
    """True if the draft uses an em- or en-dash, which reads as machine-written here."""
    return any(ch in (text or "") for ch in EM_DASH_CHARS)


def overlong_sentences(text: str, max_words: int) -> List[str]:
    """
    Sentences past the persona's limit.

    A sentence doing two jobs should be split. One live draft ran to 55 words with two
    parentheticals and read like a conference abstract.
    """
    if not text or max_words <= 0:
        return []
    long_ones = []
    for chunk in _SENTENCE_SPLIT.split(text.strip()):
        sentence = " ".join(chunk.split())
        if len(sentence.split()) > max_words:
            long_ones.append(sentence)
    return long_ones


def parenthetical_definitions(text: str) -> List[str]:
    """
    Bracketed explanations of jargon.

    Glossing a term keeps the jargon and adds a footnote. The persona rewrites the
    idea in plain words instead.
    """
    return [m.group(0)[:80] for m in PARENTHETICAL_DEFINITION.finditer(text or "")]


def closing_takeaway(text: str) -> List[str]:
    """Appended conclusions after the mechanism has already been explained."""
    found = []
    for pattern in CLOSING_TAKEAWAY_PATTERNS:
        match = pattern.search(text or "")
        if match:
            found.append(match.group(0).strip())
    return found


def scaffolding_leaks(text: str) -> List[str]:
    """Phrases where the draft describes its own structure rather than just having it."""
    found = []
    for pattern in SCAFFOLDING_PATTERNS:
        match = pattern.search(text or "")
        if match:
            found.append(match.group(0).strip())
    return found


def borrowed_phrases(draft: str, example: str, min_run: int = MIN_BORROWED_RUN_WORDS) -> List[str]:
    """
    Word runs the draft has lifted verbatim from the persona's worked example.

    The example exists to show shape. Models tend to treat it as a template and reuse
    its sentences, which makes every post sound identical and can state things simply
    untrue of the new topic.
    """
    if not draft or not example:
        return []

    draft_words = _words(draft)
    example_words = _words(example)
    if len(example_words) < min_run or len(draft_words) < min_run:
        return []

    draft_runs = {
        " ".join(draft_words[i:i + min_run])
        for i in range(len(draft_words) - min_run + 1)
    }
    joined_draft = " ".join(draft_words)

    found: List[str] = []
    i = 0
    while i <= len(example_words) - min_run:
        run = " ".join(example_words[i:i + min_run])
        if run in draft_runs:
            end = i + min_run
            while end < len(example_words):
                if joined_draft.find(" ".join(example_words[i:end + 1])) == -1:
                    break
                end += 1
            found.append(" ".join(example_words[i:end]))
            i = end
        else:
            i += 1
    return found


def score_draft(text: str, voice, worked_example: str = "") -> Tuple[int, List[str]]:
    """
    Rank drafts of the same topic against the persona's own rules.

    Used when several drafts are written from one editorial handoff and only the best
    is kept. This is deliberately the same deterministic vocabulary the QA judge
    applies, so picking a winner here means picking the one most likely to survive QA
    - rather than asking a model which of its own drafts it prefers, which it is not
    reliable at.

    Returns (score, faults). Higher is better; 100 is a draft with nothing against it.
    """
    faults: List[str] = []
    score = 100

    if voice.forbid_em_dashes and em_dashes(text):
        faults.append("uses em-dashes")
        score -= 25

    long_sentences = overlong_sentences(text, voice.max_sentence_words)
    if long_sentences:
        faults.append(f"{len(long_sentences)} sentence(s) over {voice.max_sentence_words} words")
        score -= 10 * len(long_sentences)

    if voice.forbid_parenthetical_definitions and parenthetical_definitions(text):
        faults.append("defines jargon in brackets")
        score -= 15

    if voice.forbid_closing_takeaway and closing_takeaway(text):
        faults.append("ends on a takeaway")
        score -= 20

    leaks = scaffolding_leaks(text)
    if leaks:
        faults.append(f"leaks scaffolding: {', '.join(leaks[:2])}")
        score -= 15 * len(leaks)

    lowered = text.lower()
    banned = [p for p in voice.forbidden_phrases if p.lower() in lowered]
    if banned:
        faults.append(f"forbidden phrase: {', '.join(banned[:2])}")
        score -= 20 * len(banned)

    if worked_example:
        borrowed = borrowed_phrases(text, worked_example)
        if borrowed:
            faults.append(f"borrows from the example: {borrowed[0]!r}")
            score -= 20 * len(borrowed)

    # Length is scored by distance from the band rather than pass/fail, so a draft
    # three words over loses to a clean one without being discarded outright.
    # Hashtags are excluded: they are part of the post but not part of the prose, and
    # counting them pushed otherwise well-judged drafts past the limit.
    prose = re.sub(r"\n*(?:#\w+\s*)+$", "", text).strip()
    count = len(_words(prose))
    if count < voice.min_post_words:
        faults.append(f"short at {count} words")
        score -= min(30, (voice.min_post_words - count))
    elif count > voice.max_post_words:
        faults.append(f"long at {count} words")
        score -= min(30, (count - voice.max_post_words))

    return score, faults
