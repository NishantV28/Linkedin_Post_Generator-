"""
Reputational checks on a finished draft.

The QA judge asks whether a post is well written. This asks a different question:
whether it says something about a named party that the persona cannot stand behind.
A post can be clean prose, correctly grounded in its source, and still be a claim
about a real company that nobody would want published under their own name.

Deterministic on purpose. These are the cases where a model's judgement is least
trustworthy - it will happily rate a defamatory sentence as "confident and clear" -
and where the cost of being wrong falls on a real person rather than on the feed.

Findings are advisory rather than fatal: they are attached to the draft so a reviewer
sees them before approving, since a legitimate post may well name a company while
describing its published work.
"""

import re
from typing import List, NamedTuple

# Terms that make a sentence an assertion about a party rather than a description of
# work. Deliberately narrow: "X is insecure" is a claim, "X reports a 12% gain" is not.
ABSOLUTE_CLAIM_PATTERNS = [
    r"\bis (?:dead|broken|useless|a scam|a fraud|vaporware|over)\b",
    r"\bnobody should (?:use|trust|buy)\b",
    r"\bno one should (?:use|trust|buy)\b",
    r"\bwill (?:fail|collapse|go bankrupt|be sued)\b",
    r"\b(?:always|never) (?:lies|steals|misleads)\b",
    r"\b(?:stole|stealing) (?:from|data|code|content)\b",
    r"\bknowingly (?:misled|deceived|lied)\b",
    r"\b(?:lied|lying) about\b",
    r"\bcovered up\b",
    r"\bfraudulent\b",
    r"\bnegligent\b",
    r"\bincompetent\b",
]

# Claims about people or companies that assert wrongdoing or private fact.
DEFAMATION_RISK_PATTERNS = [
    r"\bfaked (?:the |their )?(?:results|data|benchmarks?)\b",
    r"\bmanipulated (?:the |their )?(?:results|data|benchmarks?)\b",
    r"\bcherry-?picked to (?:mislead|deceive)\b",
    r"\bplagiari[sz]ed\b",
    r"\bripped off\b",
    r"\bcopied .{0,20}without (?:credit|attribution|permission)\b",
]

# Hedges that turn an assertion into an observation. A sentence carrying one of these
# is reporting or reasoning rather than declaring.
HEDGES = [
    "appears", "seems", "suggests", "reportedly", "according to", "claims",
    "may ", "might ", "could ", "likely", "arguably", "in their", "they report",
    "the paper", "the authors", "their results", "measured", "on this benchmark",
    "under these conditions", "in this test", "based on",
]

# Capitalised multi-word names and known-company shapes. Crude by design: this only
# needs to answer "does this sentence name someone", not resolve who.
_NAMED_ENTITY = re.compile(
    r"\b(?:[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*)\b"
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Words that start a sentence or appear capitalised without naming anyone, so they do
# not by themselves make a sentence a claim about a party.
_NOT_NAMES = {
    "The", "This", "That", "These", "Those", "It", "There", "Their", "They", "A", "An",
    "But", "And", "So", "What", "When", "Where", "Why", "How", "If", "Once", "Every",
    "Most", "Some", "Both", "One", "Two", "Three", "Each", "AI", "LLM", "LLMs", "GPU",
    "API", "RAG", "ML", "NLP", "CPU", "OK",
}


class SafetyFinding(NamedTuple):
    """One sentence worth a reviewer's attention, and why."""
    sentence: str
    reason: str


def _names_a_party(sentence: str) -> bool:
    """Whether the sentence appears to name a company or person."""
    for match in _NAMED_ENTITY.findall(sentence):
        head = match.split()[0]
        if head in _NOT_NAMES:
            continue
        # A single capitalised word at the very start is usually just sentence case.
        if sentence.strip().startswith(match) and " " not in match:
            continue
        return True
    return False


def _is_hedged(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(h in lowered for h in HEDGES)


def check_post(text: str) -> List[SafetyFinding]:
    """
    Sentences that assert something about a named party without hedging.

    Returns an empty list for a post that names nobody, or that attributes every
    claim to a source. A finding is a prompt to look, not a verdict.
    """
    findings: List[SafetyFinding] = []

    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue

        lowered = sentence.lower()

        for pattern in DEFAMATION_RISK_PATTERNS:
            if re.search(pattern, lowered):
                findings.append(SafetyFinding(
                    sentence=sentence,
                    reason="alleges wrongdoing - verify this is stated by the source, not by us",
                ))
                break
        else:
            # Absolutes only matter when aimed at somebody, and only when the sentence
            # states them outright. "Their benchmark suggests the approach is broken"
            # is analysis; "Acme's product is broken" is a claim about Acme.
            for pattern in ABSOLUTE_CLAIM_PATTERNS:
                if re.search(pattern, lowered) and _names_a_party(sentence) and not _is_hedged(sentence):
                    findings.append(SafetyFinding(
                        sentence=sentence,
                        reason="unhedged claim about a named party",
                    ))
                    break

    return findings


def format_findings(findings: List[SafetyFinding]) -> str:
    """A short note for the post's rationale, so a reviewer sees it in context."""
    if not findings:
        return ""
    lines = [f"- {f.reason}: \"{f.sentence[:120]}\"" for f in findings]
    return "[Brand safety - review before approving]\n" + "\n".join(lines)
