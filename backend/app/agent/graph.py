import logging
from typing import Literal
from langgraph.graph import StateGraph, END

from backend.app.agent.state import AgentState
from backend.app.agent.nodes.editorial_judge import editorial_judge_node
from backend.app.agent.nodes.writer import writer_node
from backend.app.agent.nodes.qa_judge import qa_judge_node
from backend.app.agent.nodes.publish import publish_node
from backend.app.agent.nodes.rejection_logger import log_candidate_rejection

logger = logging.getLogger("autonomous_agent.agent.graph")

# Maximum writer revisions per candidate before the topic is abandoned.
MAX_REVISIONS = 2

def start_cycle(state: AgentState) -> AgentState:
    """Initialize cycle state parameters."""
    state["candidate_idx"] = 0
    state["retry_count"] = 0
    state["rejected_count"] = 0
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

def log_rejection(state: AgentState) -> AgentState:
    """
    Persist the current candidate's rejection.

    This is a node, not a router side effect, so its `rejected_count` increment
    actually survives into the next step of the graph.
    """
    qa = state.get("qa_verdict")
    if qa and qa.verdict.lower() != "pass":
        prefix = "[QA Judge Rejected after revision limit]"
    else:
        prefix = "[Editorial Judge Rejected]"
    return log_candidate_rejection(state, reason_prefix=prefix)

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
def route_after_start(state: AgentState) -> Literal["editorial_judge", "__end__"]:
    if not state.get("current_candidate"):
        return END
    return "editorial_judge"

def route_after_judge(state: AgentState) -> Literal["writer", "log_rejection"]:
    verdict = state.get("judge_verdict")
    if verdict and verdict.decision.lower() == "pass":
        return "writer"
    return "log_rejection"

def route_after_qa(state: AgentState) -> Literal["publish", "writer", "log_rejection"]:
    qa = state.get("qa_verdict")
    retry_count = state.get("retry_count", 0)

    if qa and qa.verdict.lower() == "pass":
        return "publish"

    # `retry_count` is incremented by writer_node, so it reflects revisions
    # already performed; allow up to MAX_REVISIONS of them.
    if qa and qa.verdict.lower() == "revise" and retry_count < MAX_REVISIONS:
        logger.info(f"QA requested revision. Retrying writer node (Attempt {retry_count + 1}/{MAX_REVISIONS})")
        return "writer"

    # QA failed after retries
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
    workflow.add_node("qa_judge", qa_judge_node)
    workflow.add_node("publish", publish_node)
    workflow.add_node("log_rejection", log_rejection)
    workflow.add_node("advance_candidate", advance_candidate)

    # Set Entry Point
    workflow.set_entry_point("start_cycle")

    # Add Edges & Conditional Routing
    workflow.add_conditional_edges("start_cycle", route_after_start)
    workflow.add_conditional_edges("editorial_judge", route_after_judge)
    workflow.add_edge("writer", "qa_judge")
    workflow.add_conditional_edges("qa_judge", route_after_qa)
    workflow.add_edge("log_rejection", "advance_candidate")
    workflow.add_edge("publish", END)
    workflow.add_conditional_edges("advance_candidate", route_after_advance)

    app_graph = workflow.compile()
    return app_graph

# Expose compiled agent graph instance
agent_graph = build_agent_graph()
