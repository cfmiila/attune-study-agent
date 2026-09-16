"""
Builds the graph:

    START ─┬─▶ parse_profile ──┐
           └─▶ extract_topics ─┴─▶ build_schedule ─▶ generate_flashcards ─▶ validate ─▶ [respond | generate_flashcards]

`parse_profile` and `extract_topics` have no data dependency on each
other -- one reads `questionnaire_answers`, the other
`syllabus_text` / `free_form_goal` -- so they fan out from START and run
concurrently. `build_schedule` waits for BOTH: it needs `topics` (from
`extract_topics`) and `student_profile.study_pace` (from `parse_profile`,
via TOPIC_SPACING_DAYS). From `build_schedule` on, the pipeline is
sequential, and the `validate -> generate_flashcards` edge stays a
conditional self-correction loop (capped by MAX_FLASHCARD_RETRIES),
unchanged.

The parallel step is conflict-free: `parse_profile` writes only
`student_profile`, `extract_topics` writes only `topics` /
`topics_source` -- disjoint keys, so no reducer is needed on AgentState.
"""

from langgraph.graph import StateGraph, START, END

from app.graph.state import AgentState
from app.graph.nodes import (
    MAX_FLASHCARD_RETRIES,
    parse_profile_node,
    extract_topics_node,
    build_schedule_node,
    generate_flashcards_node,
    validate_node,
    respond_node,
)


def _route_after_validation(state: AgentState) -> str:
    """
    Decides whether to retry flashcard generation or proceed to respond.

    Retries only if there are real issues AND the retry budget isn't
    exhausted -- this cap is what prevents an infinite loop if the model
    keeps making the same kind of mistake across attempts.
    """
    if state.get("approved", True):
        return "respond"
    if state.get("retry_count", 0) >= MAX_FLASHCARD_RETRIES:
        return "respond"
    return "generate_flashcards"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("parse_profile", parse_profile_node)
    graph.add_node("extract_topics", extract_topics_node)
    graph.add_node("build_schedule", build_schedule_node)
    graph.add_node("generate_flashcards", generate_flashcards_node)
    graph.add_node("validate", validate_node)
    graph.add_node("respond", respond_node)

    # Fan-out: parse_profile and extract_topics run concurrently from START.
    graph.add_edge(START, "parse_profile")
    graph.add_edge(START, "extract_topics")

    # Fan-in: build_schedule waits for BOTH -- it reads `topics` and
    # `student_profile.study_pace`.
    graph.add_edge("parse_profile", "build_schedule")
    graph.add_edge("extract_topics", "build_schedule")

    # Sequential from here; the retry loop is unchanged.
    graph.add_edge("build_schedule", "generate_flashcards")
    graph.add_edge("generate_flashcards", "validate")
    graph.add_conditional_edges(
        "validate",
        _route_after_validation,
        {"respond": "respond", "generate_flashcards": "generate_flashcards"},
    )
    graph.add_edge("respond", END)

    return graph.compile()


agent = build_graph()
