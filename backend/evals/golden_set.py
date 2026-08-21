"""
Frozen candidates with the decision each one should get.

A prompt change is invisible until it is measured. The hashtag instruction added to
the writer is the case in point: it was one edit, it read as harmless, and it quietly
pushed drafts past the word limit so that good candidates burned all three revisions
and were dropped. Nothing failed. The feed just got thinner.

This is the ruler for that kind of change. Each case is a real candidate paired with
the decision the persona should reach and, crucially, the reason - a case that passes
for the wrong reason is a case that will stop passing later without warning.

Cases are deliberately near the boundary. A set of obvious accepts and obvious
rejects agrees with itself under any prompt and measures nothing.
"""

from typing import List, NamedTuple

from backend.app.agent.tools.schema import TopicCandidate


class GoldenCase(NamedTuple):
    """One candidate and the judgement it should receive."""
    candidate: TopicCandidate
    expected_decision: str          # "publish" or "reject"
    because: str                    # what this case is actually testing
    # Set when a specific disqualifier is the point of the case. Left None when the
    # decision matters but the precise reason legitimately varies.
    expected_disqualifier: str = None


def _candidate(idx: int, title: str, summary: str, source: str = "arxiv", url: str = None) -> TopicCandidate:
    return TopicCandidate(
        id=f"golden-{idx}",
        title=title,
        summary=summary,
        url=url or f"https://arxiv.org/abs/2608.{idx:05d}",
        source=source,
        published_at="2026-08-08T10:00:00Z",
    )


GOLDEN_SET: List[GoldenCase] = [
    # ---------------------------------------------------------------- accepts --
    GoldenCase(
        _candidate(
            1,
            "Reliability weighting recovers accuracy lost to misleading retrieved passages",
            "We show that retrieval-augmented models treat every retrieved passage as "
            "equally trustworthy. On a benchmark where one passage in five contradicts "
            "the rest, accuracy falls from 78% to 61%. Scoring each passage for "
            "agreement with the retrieved set before generation recovers 15 of those "
            "17 points, at the cost of one additional forward pass per passage.",
        ),
        "publish",
        "the archetype: one mechanism, a measured effect, a stated cost",
    ),
    GoldenCase(
        _candidate(
            2,
            "Quantised models keep their accuracy and lose their calibration",
            "Four-bit quantisation costs 2.1 points of accuracy on our suite. Expected "
            "calibration error rises by a factor of four over the same models at "
            "sixteen bits. We trace this to the flattening of the logit distribution "
            "under symmetric quantisation, and show that per-channel scaling recovers "
            "most of the calibration without recovering the accuracy.",
        ),
        "publish",
        "a finding whose interest lies in a second-order effect, not the headline number",
    ),
    GoldenCase(
        _candidate(
            3,
            "Position, not length, determines whether long-context retrieval works",
            "Reported gains from longer context windows average over the position of "
            "the relevant passage. Holding length fixed at 32k tokens and varying "
            "position, recall for a passage at the midpoint is 41%, against 88% at the "
            "start. The averaged figure of 71% describes no configuration anyone "
            "actually runs.",
        ),
        "publish",
        "corrects a widely repeated reading; the kind of post the contrarian shape exists for",
    ),

    # ---------------------------------------------------------------- rejects --
    GoldenCase(
        _candidate(
            4,
            "Introducing Acme AI Studio: the future of enterprise intelligence",
            "Acme today announced Acme AI Studio, a unified platform empowering teams "
            "to harness the transformative power of generative AI across the "
            "enterprise. Available now for all Acme Cloud customers.",
            source="web",
            url="https://example.com/blog/acme-ai-studio",
        ),
        "reject",
        "a launch announcement with no mechanism and nothing measured",
        expected_disqualifier="pure_announcement",
    ),
    GoldenCase(
        _candidate(
            5,
            "10 AI tools every developer should be using in 2026",
            "From code completion to automated testing, these ten tools are changing "
            "how developers work. Number 7 will surprise you.",
            source="web",
            url="https://example.com/blog/10-ai-tools",
        ),
        "reject",
        "a listicle: many items, no single idea to explain",
        expected_disqualifier="listicle",
    ),
    GoldenCase(
        _candidate(
            6,
            "Why I think AGI is closer than everyone believes",
            "After twenty years in the field, my instinct is that we are three years "
            "away rather than thirty. Here is why the sceptics keep getting this wrong.",
            source="hn",
            url="https://example.com/blog/agi-soon",
        ),
        "reject",
        "opinion with no evidence to explain, however interesting the claim",
        expected_disqualifier="opinion_no_evidence",
    ),
    GoldenCase(
        _candidate(
            7,
            "A faster CSS grid layout algorithm for responsive dashboards",
            "We reduce layout thrash in large dashboards by computing track sizes "
            "incrementally. Rendering time for a 400-widget dashboard falls from 210ms "
            "to 45ms.",
            source="github",
            url="https://github.com/example/fast-grid",
        ),
        "reject",
        "solid work, measured result, wrong subject for this persona",
        expected_disqualifier="off_topic",
    ),

    # ------------------------------------------------------------- boundaries --
    GoldenCase(
        _candidate(
            8,
            "Scaling laws hold for mixture-of-experts models up to 400B parameters",
            "We extend previously published scaling analysis to larger mixture-of-"
            "experts configurations and find the same power-law relationship holds, "
            "with a revised coefficient.",
        ),
        "reject",
        "confirms an existing result without changing anything - the thin end of "
        "'true but not worth saying'",
        expected_disqualifier="low_editorial_value",
    ),
    GoldenCase(
        _candidate(
            9,
            "Attention sinks explain why the first token dominates long-context recall",
            "The first token accumulates disproportionate attention mass regardless of "
            "content. We show this is a consequence of softmax normalisation over an "
            "unbounded context, demonstrate it across seven model families, and show "
            "that a single learned sink token restores uniform recall.",
        ),
        "publish",
        "a mechanism that explains something readers have already noticed",
    ),
    GoldenCase(
        _candidate(
            10,
            "New state-of-the-art on MMLU",
            "Our model achieves 92.3% on MMLU, surpassing the previous best of 91.8%.",
        ),
        "reject",
        "a benchmark number with no mechanism: the exact case the persona's premise "
        "is written against",
        expected_disqualifier="low_editorial_value",
    ),
]


def summarise() -> str:
    """One line per case, for a report header."""
    accepts = sum(1 for c in GOLDEN_SET if c.expected_decision == "publish")
    return (
        f"{len(GOLDEN_SET)} cases: {accepts} expected publish, "
        f"{len(GOLDEN_SET) - accepts} expected reject"
    )
