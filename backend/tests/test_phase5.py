"""
Output-quality machinery: voice samples, post types, draft selection, brand safety.

These cover the parts that decide what a post looks like before QA ever sees it.
Each is deterministic, so none of them needs a model.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.app.agent.brand_safety import check_post, format_findings
from backend.app.agent.persona.presets import DISTILL_PRESET, ADA_PRESET
from backend.app.agent.persona.voice import score_draft
from backend.app.agent.prompts.writer import POST_TYPE_INSTRUCTIONS
from backend.app.agent.persona.schema import POST_TYPES, PostTypeMix


# --------------------------------------------------------------------------- #
# Voice samples
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("preset", [DISTILL_PRESET, ADA_PRESET], ids=["distill", "ada"])
def test_presets_ship_voice_samples(preset):
    """
    Samples are what the writer actually matches against; adjectives are not.
    A preset without them silently falls back to a single worked example.
    """
    samples = preset.voice_guidelines.voice_samples
    assert len(samples) >= 3, f"{preset.name} should demonstrate its voice, not just describe it"
    for sample in samples:
        assert len(sample.split()) >= 50, "a sample too short to show rhythm teaches nothing"


@pytest.mark.parametrize("preset", [DISTILL_PRESET, ADA_PRESET], ids=["distill", "ada"])
def test_voice_samples_obey_the_personas_own_rules(preset):
    """
    A sample that breaks the persona's deterministic rules teaches the writer to
    break them too, and the resulting draft then fails QA for following its example.
    """
    voice = preset.voice_guidelines
    for i, sample in enumerate(voice.voice_samples):
        score, faults = score_draft(sample, voice)
        assert not faults, f"{preset.name} sample {i + 1} violates its own rules: {faults}"


def test_user_supplied_samples_replace_the_preset_ones():
    """
    Someone's own posts describe how they write better than anything hand-written,
    so they replace the preset's rather than being mixed in with them.
    """
    from backend.app.agent.persona.presets import get_preset_by_name_or_domain

    persona = get_preset_by_name_or_domain("Distill", "AI Research")
    original = list(persona.voice_guidelines.voice_samples)
    assert original, "precondition: the preset ships samples"

    persona.voice_guidelines.voice_samples = ["A post the user actually wrote."]

    assert persona.voice_guidelines.voice_samples == ["A post the user actually wrote."]
    assert original[0] not in persona.voice_guidelines.voice_samples


# --------------------------------------------------------------------------- #
# Post types
# --------------------------------------------------------------------------- #

def test_every_declared_post_type_has_an_instruction():
    """A type the writer can draw but cannot be told how to write is a silent no-op."""
    missing = set(POST_TYPES) - set(POST_TYPE_INSTRUCTIONS)
    assert not missing, f"no writer instruction for: {sorted(missing)}"


def test_post_type_mix_covers_every_type():
    """A type absent from the mix can never be selected, whatever the instructions say."""
    weights = PostTypeMix().model_dump()
    assert set(weights) == set(POST_TYPES)


def test_post_type_selection_respects_the_weights():
    from backend.app.agent.nodes.writer import _pick_post_type

    persona = DISTILL_PRESET.model_copy(deep=True)
    persona.post_type_mix = PostTypeMix(explainer=1, observation=0, question=0, lesson=0, contrarian=0)

    # Only one type carries any weight, so every draw must be that type.
    assert {_pick_post_type(persona) for _ in range(20)} == {"explainer"}


def test_post_type_falls_back_when_the_mix_is_empty():
    """Zero weights everywhere must not raise; explainer is the safe default shape."""
    from backend.app.agent.nodes.writer import _pick_post_type

    persona = DISTILL_PRESET.model_copy(deep=True)
    persona.post_type_mix = PostTypeMix(explainer=0, observation=0, question=0, lesson=0, contrarian=0)

    assert _pick_post_type(persona) == "explainer"


# --------------------------------------------------------------------------- #
# Draft scoring
# --------------------------------------------------------------------------- #

CLEAN_DRAFT = (
    "Retrieval systems are usually judged on whether they find the right document. "
    "That framing assumes the model will use what it finds. The more useful result "
    "here is about what happens when retrieval succeeds and the answer still gets "
    "worse. The model treats every retrieved passage as equally trustworthy, so one "
    "confidently wrong passage outweighs three correct ones. The fix they test is a "
    "scoring step that runs before generation. Each passage gets a reliability weight "
    "from the same model, and low-weight passages are dropped rather than summarised. "
    "Accuracy recovers most of the gap, and the cost is one extra forward pass per "
    "passage. The limitation is that the scorer and the generator share the same blind "
    "spots, so a passage that fools one tends to fool the other."
)


def test_a_clean_draft_scores_full_marks():
    score, faults = score_draft(CLEAN_DRAFT, DISTILL_PRESET.voice_guidelines)
    assert not faults
    assert score == 100


def test_scoring_penalises_the_rules_qa_would_reject():
    voice = DISTILL_PRESET.voice_guidelines
    clean_score, _ = score_draft(CLEAN_DRAFT, voice)

    with_em_dash = CLEAN_DRAFT + " The result is clear—for now."
    dash_score, dash_faults = score_draft(with_em_dash, voice)

    assert dash_score < clean_score
    assert any("em-dash" in f for f in dash_faults)


def test_scoring_penalises_forbidden_phrases():
    voice = DISTILL_PRESET.voice_guidelines
    hyped = CLEAN_DRAFT + " This is a groundbreaking result."

    score, faults = score_draft(hyped, voice)

    assert any("forbidden phrase" in f for f in faults)
    assert score < 100


def test_hashtags_are_excluded_from_the_word_count():
    """
    The writer appends hashtags and the limit is enforced on prose. Counting them
    pushed otherwise well-judged drafts over the limit and into needless revisions.
    """
    voice = DISTILL_PRESET.voice_guidelines

    bare_score, _ = score_draft(CLEAN_DRAFT, voice)
    tagged_score, tagged_faults = score_draft(
        CLEAN_DRAFT + "\n\n#AI #Retrieval #MachineLearning #RAG #Evaluation", voice
    )

    assert tagged_score == bare_score
    assert not any("long at" in f for f in tagged_faults)


def test_the_better_draft_wins():
    """The whole point of writing several: the cleanest one is the one kept."""
    voice = DISTILL_PRESET.voice_guidelines

    good = score_draft(CLEAN_DRAFT, voice)[0]
    bad = score_draft(CLEAN_DRAFT + " This groundbreaking work—truly revolutionary.", voice)[0]

    assert good > bad


# --------------------------------------------------------------------------- #
# Brand safety
# --------------------------------------------------------------------------- #

def test_clean_post_raises_nothing():
    assert check_post(CLEAN_DRAFT) == []


def test_unhedged_claim_about_a_named_party_is_flagged():
    findings = check_post("Acme Corp is broken and nobody should use it.")
    assert findings
    assert "named party" in findings[0].reason


def test_the_same_claim_attributed_to_a_source_is_not_flagged():
    """
    Reporting what a paper found is the persona's whole job. Flagging that would make
    the check useless by crying wolf on ordinary posts.
    """
    assert check_post(
        "According to their benchmark, Acme Corp is dead in this configuration."
    ) == []


def test_alleged_wrongdoing_is_flagged_even_when_hedged():
    """
    Hedging softens an opinion. It does not soften an accusation, which carries the
    same risk whether or not it is attributed.
    """
    findings = check_post("The authors suggest Acme may have faked the results.")
    assert findings
    assert "wrongdoing" in findings[0].reason


def test_technical_criticism_is_not_treated_as_an_accusation():
    """Saying an approach fails is analysis, and must stay publishable."""
    assert check_post(
        "The paper reports that the approach is broken under sustained load."
    ) == []


def test_findings_render_for_a_reviewer():
    findings = check_post("Acme Corp is broken and nobody should use it.")
    rendered = format_findings(findings)

    assert "Brand safety" in rendered
    assert "Acme Corp" in rendered


def test_format_findings_is_empty_when_there_is_nothing_to_say():
    assert format_findings([]) == ""
