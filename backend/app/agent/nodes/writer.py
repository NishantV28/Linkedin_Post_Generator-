import logging
import random

from backend.app.agent.state import AgentState, DraftPost
from backend.app.agent.llm import get_structured_llm
from backend.app.core.config import settings
from backend.app.memory.db import SessionLocal
from backend.app.memory.hybrid_retriever import HybridRetriever
from backend.app.agent.persona.voice import score_draft
from backend.app.agent.prompts.writer import (
    WRITER_SYSTEM_PROMPT,
    WRITER_USER_PROMPT,
    POST_TYPE_INSTRUCTIONS,
)

logger = logging.getLogger("autonomous_agent.agent.nodes.writer")

FEW_SHOT_POSTS = 2

# Angles used when drafting more than once. Each produces a genuinely different post
# from the same editorial handoff rather than a reworded one, which is the point:
# revising a single draft converges on "less wrong", while separate attempts can
# find "better".
DRAFT_ANGLES = ["explainer", "lesson", "contrarian"]


def _pick_post_type(persona) -> str:
    """
    Choose this post's shape from the persona's weighted mix.

    Weighted rather than a fixed rotation, so a feed does not become predictable, and
    so a persona can lean heavily on one shape without ever excluding the others.
    """
    mix = getattr(persona, "post_type_mix", None)
    if mix is None:
        return "explainer"

    weights = mix.model_dump()
    types = [t for t, w in weights.items() if w > 0]
    if not types:
        return "explainer"
    return random.choices(types, weights=[weights[t] for t in types], k=1)[0]


def _format_voice_samples(persona) -> str:
    """The persona's example posts, or a clear statement that there are none."""
    samples = getattr(persona.voice_guidelines, "voice_samples", None) or []
    if not samples:
        return "(No samples supplied. Follow the worked example above.)"
    return "\n\n---\n\n".join(samples)


def _few_shot_context(agent_id: str, query_text: str) -> str:
    """Past posts most related to this topic, used as a voice anchor."""
    if not agent_id:
        return "No posts published yet. Match the tone of the example above."
    db = SessionLocal()
    try:
        posts = HybridRetriever.get_relevant_context(
            agent_id=agent_id, query_text=query_text, db=db, top_k=FEW_SHOT_POSTS
        )
        if not posts:
            return "No posts published yet. Match the tone of the example above."
        return "\n\n".join(f"- {p['text']}" for p in posts)
    except Exception as err:
        logger.debug(f"Could not retrieve few-shot context: {err}")
        return "No posts published yet. Match the tone of the example above."
    finally:
        db.close()


def writer_node(state: AgentState) -> AgentState:
    """
    Render the judge's editorial decision as a post.

    The writer does not choose the topic or the angle. It receives a settled
    writer_context and turns it into prose, which is what keeps a post tied to the
    source the judge actually approved.
    """
    persona = state["persona"]
    verdict = state.get("judge_verdict")
    qa_verdict = state.get("qa_verdict")
    retry_count = state.get("retry_count", 0)

    if not verdict or not verdict.writer_context:
        logger.warning("writer_node called without an editorial handoff.")
        state["draft"] = None
        state["node_error"] = "writer: no writer_context from the editorial judge"
        return state

    ctx = verdict.writer_context

    # Count the revision here rather than in the router: LangGraph rebuilds state for
    # conditional-edge functions, so mutations made there are never persisted.
    if qa_verdict and qa_verdict.verdict == "revise":
        retry_count += 1
        state["retry_count"] = retry_count

    try:
        voice = persona.voice_guidelines

        # A revision keeps the shape the first draft was written in. Switching mid-way
        # would answer QA's feedback with a different post rather than a fixed one.
        post_type = state.get("post_type") or _pick_post_type(persona)
        state["post_type"] = post_type

        system_msg = WRITER_SYSTEM_PROMPT.format(
            persona_name=persona.name,
            persona_domain=persona.domain,
            persona_bio=persona.bio,
            core_question=voice.core_question or "What does this actually change?",
            tone=voice.tone,
            sentence_rhythm=voice.sentence_rhythm,
            stable_interests=", ".join(persona.stable_interests) or "None",
            forbidden_phrases=", ".join(voice.forbidden_phrases) or "None",
            worked_example=voice.worked_example or "(no example available)",
            voice_samples=_format_voice_samples(persona),
            post_type_instruction=POST_TYPE_INSTRUCTIONS.get(
                post_type, POST_TYPE_INSTRUCTIONS["explainer"]
            ),
            few_shot_context=_few_shot_context(
                state.get("agent_id", ""), f"{ctx.core_claim} {ctx.mechanism}"
            ),
            min_words=voice.min_post_words,
            max_words=voice.max_post_words,
            max_sentence_words=voice.max_sentence_words,
        )

        revision_section = ""
        if qa_verdict and qa_verdict.verdict == "revise":
            revision_section = (
                f"REVISION REQUEST (attempt {retry_count}):\n{qa_verdict.feedback}\n"
                "Fix all of these in this rewrite."
            )

        user_msg = WRITER_USER_PROMPT.format(
            editorial_angle=verdict.editorial_angle,
            obvious_assumption=ctx.obvious_assumption,
            interesting_turn=ctx.interesting_turn,
            core_claim=ctx.core_claim,
            mechanism=ctx.mechanism,
            evidence="\n".join(f"- {e}" for e in ctx.evidence) or "None supplied.",
            limitations="\n".join(f"- {l}" for l in ctx.limitations) or "None supplied.",
            persona_relevance=ctx.persona_relevance,
            why_now=ctx.why_now or "No specific timeliness evidence. Do not invent any.",
            sources="\n".join(ctx.sources) or "None",
            revision_feedback_section=revision_section,
        )

        structured_llm = get_structured_llm(DraftPost, temperature=0.6)

        # How many attempts to make at this post. More than one only on the first
        # pass: once QA has given feedback the job is to fix a specific draft, and
        # generating alternatives would discard the thing being corrected.
        attempts = 1 if retry_count else max(1, settings.WRITER_DRAFT_ATTEMPTS)

        candidates = []
        for i in range(attempts):
            angle_note = ""
            if attempts > 1 and i > 0:
                # Later attempts are pushed towards a different shape, so the choice
                # is between genuinely different posts rather than three near-copies.
                angle = DRAFT_ANGLES[i % len(DRAFT_ANGLES)]
                angle_note = (
                    f"\n\nFor this attempt, take this shape instead: "
                    f"{POST_TYPE_INSTRUCTIONS[angle]}"
                )

            try:
                candidate: DraftPost = structured_llm.invoke([
                    ("system", system_msg),
                    ("user", user_msg + angle_note),
                ])
            except Exception as attempt_error:
                # One failed attempt out of several is survivable; only every attempt
                # failing is a real problem, handled by the empty check below.
                logger.warning(f"Draft attempt {i + 1}/{attempts} failed: {attempt_error}")
                continue

            score, faults = score_draft(
                candidate.text, voice, voice.worked_example or ""
            )
            candidates.append((score, faults, candidate))
            logger.debug(
                f"Draft attempt {i + 1}/{attempts}: score {score}"
                + (f", faults: {'; '.join(faults)}" if faults else ", clean")
            )

        if not candidates:
            raise RuntimeError(f"all {attempts} draft attempt(s) failed")

        # Highest score wins. Ties keep the earlier draft, which was written in the
        # persona's own chosen shape rather than a nudged alternative.
        best_score, best_faults, draft = max(candidates, key=lambda c: c[0])

        # Sources are the judge's, not the model's. Letting the writer supply them
        # risks a post citing material it was never given.
        draft.sources = list(ctx.sources)

        if attempts > 1:
            logger.info(
                f"Writer picked the best of {len(candidates)} drafts "
                f"(score {best_score}, type '{post_type}')"
                + (f"; remaining faults: {'; '.join(best_faults)}" if best_faults else "; clean")
            )
        logger.info(
            f"Writer drafted '{verdict.editorial_angle[:50]}...' "
            f"({len(draft.text.split())} words, type '{post_type}')"
        )
        state["draft"] = draft

    except Exception as e:
        # No fallback draft: a template that ignores the persona's voice would put
        # off-voice filler into the graded feed on any API blip.
        logger.error(f"Writer could not draft: {e}", exc_info=True)
        state["draft"] = None
        state["node_error"] = f"writer: {e}"

    return state
