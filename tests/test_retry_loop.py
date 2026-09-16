"""
Tests for the self-correction retry loop: when validate_node finds
issues, the graph should loop back to generate_flashcards_node (with
feedback about what went wrong) instead of just flagging the problem
and moving on -- up to a retry limit, so it can never loop forever.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.graph.graph import _route_after_validation, agent
from app.graph.nodes import MAX_FLASHCARD_RETRIES, generate_flashcards_node


# ---------------------------------------------------------------------
# Unit tests for the routing decision (pure function, no LLM/graph needed)
# ---------------------------------------------------------------------

def test_route_goes_to_respond_when_approved():
    state = {"approved": True, "retry_count": 0}
    assert _route_after_validation(state) == "respond"


def test_route_retries_when_issues_found_and_budget_available():
    state = {"approved": False, "retry_count": 1}
    assert MAX_FLASHCARD_RETRIES > 1  # sanity check the test is meaningful
    assert _route_after_validation(state) == "generate_flashcards"


def test_route_stops_retrying_once_limit_reached():
    state = {"approved": False, "retry_count": MAX_FLASHCARD_RETRIES}
    assert _route_after_validation(state) == "respond"


# ---------------------------------------------------------------------
# generate_flashcards_node should include retry feedback when retrying
# ---------------------------------------------------------------------

def test_generate_flashcards_includes_previous_issues_in_prompt_on_retry():
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {"flashcards": [{"topic": "Ratios", "front": "f", "back": "b", "difficulty": "easy"}]}
    )

    state = {
        "topics": ["Ratios"],
        "student_profile": {
            "works": "no",
            "interests": [],
            "region": "rural area",
            "study_pace": "moderate",
            "free_context": "",
        },
        "issues_found": [
            {
                "issue_type": "forced_contextualization",
                "description": "More musicians recording faster is backwards for inverse proportion",
                "affected_excerpt": "musicians/album analogy",
            }
        ],
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        generate_flashcards_node(state)
        prompt_sent = mock_llm.return_value.invoke.call_args[0][0]

    assert "IMPORTANT" in prompt_sent
    assert "musicians recording faster is backwards" in prompt_sent


def test_generate_flashcards_has_no_retry_feedback_on_first_attempt():
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {"flashcards": [{"topic": "Ratios", "front": "f", "back": "b", "difficulty": "easy"}]}
    )

    state = {
        "topics": ["Ratios"],
        "student_profile": {
            "works": "no",
            "interests": [],
            "region": "rural area",
            "study_pace": "moderate",
            "free_context": "",
        },
        # no "issues_found" key -- first attempt, nothing to avoid yet
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        generate_flashcards_node(state)
        prompt_sent = mock_llm.return_value.invoke.call_args[0][0]

    assert "IMPORTANT" not in prompt_sent


# ---------------------------------------------------------------------
# Full graph integration: the retry loop actually runs end-to-end
# ---------------------------------------------------------------------

def _fake_llm_response(content: dict) -> MagicMock:
    response = MagicMock()
    response.content = json.dumps(content)
    return response


def _dispatch_llm(*, profile, topics, flashcards_by_attempt, issues_by_attempt):
    """
    Builds a `side_effect` callable for the mocked `_llm().invoke` that
    routes by the *content* of the prompt, not by call order.

    parse_profile and extract_topics now fan out from START and run
    concurrently, so their two LLM calls can arrive in either order (and,
    depending on the executor, from different threads). Routing on the
    prompt text keeps these tests order-independent. `flashcards_by_attempt`
    and `issues_by_attempt` are consumed one per retry attempt; the last
    entry repeats if the loop runs more attempts than entries provided.
    """
    counters = {"flashcards": 0, "validate": 0}

    def _invoke(prompt, *_args, **_kwargs):
        text = prompt if isinstance(prompt, str) else str(prompt)
        if "structured profile" in text:
            return _fake_llm_response(profile)
        if "list of study topics" in text or "topic breakdown" in text:
            return _fake_llm_response(topics)
        if "study flashcards for EACH" in text:
            i = min(counters["flashcards"], len(flashcards_by_attempt) - 1)
            counters["flashcards"] += 1
            return _fake_llm_response(flashcards_by_attempt[i])
        if "Review these study flashcards" in text:
            i = min(counters["validate"], len(issues_by_attempt) - 1)
            counters["validate"] += 1
            return _fake_llm_response(issues_by_attempt[i])
        raise AssertionError(f"unexpected prompt to mocked LLM: {text[:120]!r}")

    return _invoke


def test_graph_retries_and_corrects_after_validation_failure():
    """
    Simulates a full run where the first flashcard attempt fails
    validation, the graph loops back to generate_flashcards with the
    failure as context, and the second attempt passes -- covers
    "issue on attempt 1, none on attempt 2" end-to-end, not just the
    routing function in isolation.
    """
    dispatch = _dispatch_llm(
        profile={"works": "no", "interests": ["soccer"], "region": "Bahia",
                 "study_pace": "moderate", "free_context": ""},
        topics={"topics": ["Ratios"]},
        flashcards_by_attempt=[
            {"flashcards": [{"topic": "Ratios", "front": "f1", "back": "bad analogy", "difficulty": "easy"}]},
            {"flashcards": [{"topic": "Ratios", "front": "f1", "back": "good example", "difficulty": "easy"}]},
        ],
        issues_by_attempt=[
            {"issues": [{"issue_type": "forced_contextualization",
                         "description": "bad analogy", "affected_excerpt": "bad analogy"}]},
            {"issues": []},
        ],
    )

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.side_effect = dispatch
        result = agent.invoke(
            {
                "questionnaire_answers": "I like soccer, live in rural Bahia",
                "syllabus_text": "1. Ratios",
                "start_date": "2026-09-01",
            }
        )

    assert result["approved"] is True
    assert result["retry_count"] == 1  # one failed attempt, then corrected
    assert result["flashcards"][0]["back"] == "good example"
    # profile + topics + 2x generate_flashcards + 2x validate
    assert mock_llm.return_value.invoke.call_count == 6


def test_graph_gives_up_after_max_retries_without_infinite_loop():
    """
    If every attempt keeps failing validation, the graph must stop at
    MAX_FLASHCARD_RETRIES total attempts and proceed to respond anyway
    -- covers "limit reached, don't loop forever".
    """
    dispatch = _dispatch_llm(
        profile={"works": "no", "interests": [], "region": "Bahia",
                 "study_pace": "moderate", "free_context": ""},
        topics={"topics": ["Ratios"]},
        flashcards_by_attempt=[
            {"flashcards": [{"topic": "Ratios", "front": "f1", "back": "bad analogy", "difficulty": "easy"}]},
        ],
        issues_by_attempt=[
            {"issues": [{"issue_type": "forced_contextualization",
                         "description": "still bad", "affected_excerpt": "bad analogy"}]},
        ],
    )

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.side_effect = dispatch
        result = agent.invoke(
            {
                "questionnaire_answers": "I like soccer, live in rural Bahia",
                "syllabus_text": "1. Ratios",
                "start_date": "2026-09-01",
            }
        )

    assert result["approved"] is False  # never got fixed
    assert result["retry_count"] == MAX_FLASHCARD_RETRIES  # stopped exactly at the cap
    # Worst case = parse_profile + extract_topics (2) then MAX_FLASHCARD_RETRIES
    # rounds of generate_flashcards + validate. Derived from the constant so it
    # tracks any future change to the retry budget.
    assert mock_llm.return_value.invoke.call_count == 2 + 2 * MAX_FLASHCARD_RETRIES
    # The student still gets a result (not stuck in a loop) -- respond_node ran:
    assert "flashcards_html" in result
