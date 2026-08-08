"""
Deterministic checks and repairs for persona voice rules.

Anything that can be decided by inspecting the text belongs here rather than in a
prompt: it is cheaper, it cannot drift between runs, and it does not consume a
revision round-trip.
"""

# A closing line long enough to be a paragraph is a summary, not a takeaway.
MAX_CLOSING_LINE_WORDS = 30


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
