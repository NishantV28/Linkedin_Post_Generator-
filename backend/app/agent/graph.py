import logging
from typing import Literal
from langgraph.graph import StateGraph, END

from backend.app.agent.state import AgentState
from backend.app.agent.nodes.editorial_judge import editorial_judge_node
from backend.app.agent.nodes.writer import writer_node
from backend.app.agent.nodes.reflection_writer import reflection_writer_node
from backend.app.agent.nodes.qa_judge import qa_judge_node
from backend.app.agent.nodes.publish import publish_node
from backend.app.agent.nodes.rejection_logger import log_candidate_rejection

logger = logging.getLogger("autonomous_agent.agent.graph")

# Maximum writer revisions per candidate before the topic is abandoned.
MAX_REVISIONS = 2

def start_cycle(state: AgentState) -> AgentState:
    """Initialize cycle state parameters."""
    state.setdefault("mode", "topic")
    state["candidate_idx"] = 0
    state["retry_count"] = 0
    state["rejected_count"] = 0
    state["rejected_this_cycle"] = []
    state["node_error"] = None
    state["published_post"] = None
    state["cycle_outcome"] = "in_progress"

    candidates = state.get("candidates", [])
    if candidates:
        state["current_candidate"] = candidates[0]
        logger.info(f"Starting cycle with {len(candidates)} candidate(s). Target [0]: '{candidates[0].title[:40]}...'")
    else:
        state["current_candidate"] = None
        state["cycle_outcome"] = "no_candidates"
        logger.info("Cycle started with 0 candidates.")

    return state

def abort_cycle(state: AgentState) -> AgentState:
    """
    End the cycle after an infrastructure failure.

    A rate limit or outage will hit every remaining candidate too, so continuing only
    burns quota and fills the rejection log with errors disguised as editorial calls.
    The scheduler records the outcome and simply tries again next cycle.
    """
    error = state.get("node_error", "unknown error")
    logger.error(f"Aborting cycle after infrastructure failure - {error}")
    state["cycle_outcome"] = f"aborted_error: {str(error)[:120]}"
    return state


def log_rejection(state: AgentState) -> AgentState:
    """
    Persist the current candidate's rejection.

    This is a node, not a router side effect, so its state updates - the rejection
    count and the running list of passed-over candidates - survive into the next step.
    """
    return log_candidate_rejection(state)

def advance_candidate(state: AgentState) -> AgentState:
    """Advance candidate pointer to the next topic candidate."""
    idx = state.get("candidate_idx", 0) + 1
    state["candidate_idx"] = idx
    state["retry_count"] = 0
    state["judge_verdict"] = None
    state["draft"] = None
    state["qa_verdict"] = None

    candidates = state.get("candidates", [])
    if idx < len(candidates):
        state["current_candidate"] = candidates[idx]
        logger.info(f"Advancing to candidate [{idx}/{len(candidates)}]: '{candidates[idx].title[:40]}...'")
    else:
        state["current_candidate"] = None
        state["cycle_outcome"] = "all_rejected"
        logger.info("All candidate topics evaluated and exhausted for this cycle.")

    return state

# Routing logic functions
def route_after_start(state: AgentState) -> Literal["editorial_judge", "reflection_writer", "__end__"]:
    # A reflection post is about the agent's own coverage, so it needs no candidate
    # and skips editorial judgement - but still goes through QA like any other post.
    if state.get("mode") == "reflection" and state.get("coverage_trend"):
        return "reflection_writer"
    if not state.get("current_candidate"):
        return END
    return "editorial_judge"

def route_after_judge(state: AgentState) -> Literal["writer", "log_rejection", "abort_cycle"]:
    if state.get("node_error"):
        return "abort_cycle"
    verdict = state.get("judge_verdict")
    if verdict and verdict.decision.lower() == "pass":
        return "writer"
    return "log_rejection"

def route_after_writer(state: AgentState) -> Literal["qa_judge", "abort_cycle"]:
    if state.get("node_error"):
        return "abort_cycle"
    return "qa_judge"

def route_after_qa(state: AgentState) -> Literal["publish", "writer", "reflection_writer", "log_rejection", "abort_cycle"]:
    if state.get("node_error"):
        return "abort_cycle"

    qa = state.get("qa_verdict")
    retry_count = state.get("retry_count", 0)
    is_reflection = state.get("mode") == "reflection"

    if qa and qa.verdict.lower() == "pass":
        return "publish"

    # `retry_count` is incremented by the writing node, so it reflects revisions
    # already performed; allow up to MAX_REVISIONS of them.
    if qa and qa.verdict.lower() == "revise" and retry_count < MAX_REVISIONS:
        logger.info(f"QA requested revision. Retrying (Attempt {retry_count + 1}/{MAX_REVISIONS})")
        return "reflection_writer" if is_reflection else "writer"

    # A reflection that cannot pass QA is abandoned; there is no next candidate to
    # advance to, and publishing an unreviewed one is worse than staying quiet.
    if is_reflection:
        logger.info("Reflection post failed QA after revisions. Skipping this cycle.")
        return "abort_cycle"

    return "log_rejection"

def route_after_advance(state: AgentState) -> Literal["editorial_judge", "__end__"]:
    if state.get("current_candidate"):
        return "editorial_judge"
    return END

# Build LangGraph StateGraph
def build_agent_graph():
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("start_cycle", start_cycle)
    workflow.add_node("editorial_judge", editorial_judge_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("reflection_writer", reflection_writer_node)
    workflow.add_node("qa_judge", qa_judge_node)
    workflow.add_node("publish", publish_node)
    workflow.add_node("log_rejection", log_rejection)
    workflow.add_node("abort_cycle", abort_cycle)
    workflow.add_node("advance_candidate", advance_candidate)

    # Set Entry Point
    workflow.set_entry_point("start_cycle")

    # Add Edges & Conditional Routing
    workflow.add_conditional_edges("start_cycle", route_after_start)
    workflow.add_conditional_edges("editorial_judge", route_after_judge)
    workflow.add_conditional_edges("writer", route_after_writer)
    workflow.add_conditional_edges("reflection_writer", route_after_writer)
    workflow.add_conditional_edges("qa_judge", route_after_qa)
    workflow.add_edge("log_rejection", "advance_candidate")
    workflow.add_edge("abort_cycle", END)
    workflow.add_edge("publish", END)
    workflow.add_conditional_edges("advance_candidate", route_after_advance)

    app_graph = workflow.compile()
    return app_graph

# Expose compiled agent graph instance
agent_graph = build_agent_graph()
