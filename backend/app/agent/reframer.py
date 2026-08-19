import logging
from typing import Optional
from langchain_core.messages import SystemMessage, HumanMessage
from backend.app.agent.llm import get_llm

logger = logging.getLogger("autonomous_agent.agent.reframer")

REFRAME_SYSTEM_PROMPT = """You are an expert LinkedIn editorial copywriter and restructuring assistant for {persona_name}, who writes about {persona_domain}.

{persona_bio}

TASK:
You are reframing and restructuring an existing drafted/published LinkedIn post based on direct HUMAN FEEDBACK / EDITORIAL REVIEW from the user.

GUIDELINES:
1. Incorporate the human review instructions thoroughly and directly (e.g. re-angle the message, restructure with bullet points, alter tone/pacing, make it punchier, simplify technical depth, or emphasize a specific takeaway).
2. Maintain factual accuracy: do not invent benchmarks, false claims, or fake statistics that were not present in the original post or feedback.
3. Keep the writing professional, insightful, and natural for LinkedIn.
4. Always conclude the post with 3 to 5 relevant topic hashtags (e.g. #AI #MachineLearning #TechTrends).
5. Output ONLY the finalized post text. Do not include meta-commentary like "Here is the revised post:" or markdown wrapping tags unless intended as part of the post.
"""

REFRAME_USER_PROMPT = """ORIGINAL POST:
{original_text}

HUMAN FEEDBACK / EDITORIAL REVIEW:
{user_feedback}

Please reframe and restructure the post now according to this feedback.
"""


def reframe_post(
    original_text: str,
    user_feedback: str,
    persona_name: str = "Ada Engine",
    persona_domain: str = "Technology & AI",
    persona_bio: Optional[str] = None
) -> str:
    """
    Reframes and restructures a post text based on human feedback.
    """
    llm = get_llm(temperature=0.6)
    
    system_content = REFRAME_SYSTEM_PROMPT.format(
        persona_name=persona_name,
        persona_domain=persona_domain,
        persona_bio=persona_bio or f"{persona_name} is an expert in {persona_domain}."
    )
    
    user_content = REFRAME_USER_PROMPT.format(
        original_text=original_text,
        user_feedback=user_feedback
    )
    
    logger.info(f"Reframing post for persona '{persona_name}' based on feedback: '{user_feedback[:80]}...'")
    
    response = llm.invoke([
        SystemMessage(content=system_content),
        HumanMessage(content=user_content)
    ])
    
    reframed_text = response.content if isinstance(response.content, str) else str(response.content)
    return reframed_text.strip()
