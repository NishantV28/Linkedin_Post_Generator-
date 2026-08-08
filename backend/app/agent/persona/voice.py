"""
Deterministic checks and repairs for persona voice rules.

Anything that can be decided by inspecting the text belongs here rather than in a
prompt: it is cheaper, it cannot drift between runs, and it does not consume a
revision round-trip.
"""

import re
from typing import List

# A closing line long enough to be a paragraph is a summary, not a takeaway.
MAX_CLOSING_LINE_WORDS = 30

# Shortest run of shared words treated as copying rather than coincidence. Five is
# long enough that ordinary phrasing ("it is worth noting that") does not trip it.
MIN_BORROWED_RUN_WORDS = 5


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def borrowed_phrases(draft: str, example: str, min_run: int = MIN_BORROWED_RUN_WORDS) -> List[str]:
    """
    Word runs the draft has lifted verbatim from the persona's worked example.

    The example exists to show the shape of a post. Models tend to treat it as a
    template and reuse its sentences, which makes every post sound identical and can
    state things that are simply untrue of the new topic - describing a forum thread
    as "another paper", or referring to a "benchmark score" that does not exist.
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

    found: List[str] = []
    i = 0
    while i <= len(example_words) - min_run:
        run = " ".join(example_words[i:i + min_run])
        if run in draft_runs:
            # Extend to report the longest matching run rather than a fragment.
            end = i + min_run
            while end < len(example_words):
                longer = " ".join(example_words[i:end + 1])
                if " ".join(_words(draft)).find(longer) == -1:
                    break
                end += 1
            found.append(" ".join(example_words[i:end]))
            i = end
        else:
            i += 1
    return found


def has_standalone_closing_line(text: str) -> bool:
    """
    True when the draft ends with a short, self-contained line set off from the body
    by a blank line - the persona's signature closing beat.
    """
    blocks = [b.strip() for b in text.strip().split("\n\n") if b.strip()]
    if len(blocks) < 2:
        return False
    closing = blocks[-1]
    if "\n" in closing:  # a multi-line block is a paragraph, not a standalone line
        return False
    return len(closing.split()) <= MAX_CLOSING_LINE_WORDS


def ensure_closing_line_separation(text: str) -> str:
    """
    Promote a trailing takeaway line into its own block.

    Models reliably produce the right closing *sentence* but often separate it with a
    single newline instead of a blank line. That is a formatting slip, not a writing
    failure, so it is repaired here instead of spending a revision round-trip on it.

    Only applied when the final line is already short enough to be a takeaway; a long
    rambling final paragraph is a real structural failure and is left for QA to catch.
    """
    text = text.strip()
    if "\n\n" in text:
        return text

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < 2:
        return text

    if len(lines[-1].split()) <= MAX_CLOSING_LINE_WORDS:
        return "\n".join(lines[:-1]) + "\n\n" + lines[-1]

    return text
