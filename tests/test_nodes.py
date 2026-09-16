"""
Pipeline tests. Mocks ChatGoogleGenerativeAI for nodes that call the
LLM, and tests the deterministic schedule/ICS logic directly (which
doesn't depend on the LLM, so it doesn't need mocking).
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.graph.nodes import (
    ALLOWED_CARD_TYPES,
    CARD_TYPES,
    CARDS_PER_TOPIC,
    REVIEW_INTERVALS,
    TOPIC_SPACING_DAYS,
    _build_ics,
    _parse_json_response,
    extract_topics_node,
    generate_flashcards_node,
    build_schedule_node,
    parse_profile_node,
    respond_node,
    validate_node,
)


def test_parse_json_response_tolerates_trailing_comma():
    """Small models sometimes emit a trailing comma before a closing } or ]
    on long payloads -- this is the exact shape that crashed a live
    `evaluate.py` run (JSONDecodeError: Expecting property name enclosed in
    double quotes). It must now parse without raising."""
    raw = (
        '{"topic_explanations": {"A": "x",}, '
        '"flashcards": [{"topic": "A", "type": "QA", "front": "f", "back": "b", '
        '"difficulty": "easy", "used_interest": "",}],}'
    )
    parsed = _parse_json_response(raw)
    assert parsed["flashcards"][0]["topic"] == "A"
    assert parsed["topic_explanations"] == {"A": "x"}


def test_parse_json_response_handles_trailing_comma_inside_fenced_block():
    raw = '```json\n{"topics": ["a", "b",],}\n```'
    assert _parse_json_response(raw) == {"topics": ["a", "b"]}


def test_parse_json_response_still_raises_on_genuinely_broken_json():
    """The repair pass is narrow: a truncated object (no closing brace) is
    not a trailing-comma problem, so it must still raise rather than be
    silently masked."""
    with pytest.raises(json.JSONDecodeError):
        _parse_json_response('{"topics": ["a", "b"')


def test_parse_profile_extracts_structure():
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {
            "works": "yes, as a salesperson",
            "interests": ["soccer", "cooking"],
            "region": "rural Bahia",
            "free_context": "studies at night",
        }
    )

    state = {"questionnaire_answers": "I work as a salesperson, I like soccer..."}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = parse_profile_node(state)

    assert result["student_profile"]["works"] == "yes, as a salesperson"
    assert "soccer" in result["student_profile"]["interests"]


def test_parse_profile_works_with_portuguese_input():
    """
    The questionnaire is interpreted by the LLM, not by fixed/regex
    parsing -- so a real target user (who answers in Portuguese, from
    different regions of Brazil) should work just as well as an
    English-language test case. This test documents that expectation
    explicitly, even though the LLM call itself is mocked here.
    """
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {
            "works": "sim, trabalho na roça com mandioca",
            "interests": ["forró", "futebol"],
            "region": "interior do Ceará",
            "free_context": "estuda à noite",
        }
    )

    state = {
        "questionnaire_answers": "Trabalho na roça com plantação de mandioca, "
        "gosto de forró e futebol, moro no interior do Ceará."
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = parse_profile_node(state)

    assert "forró" in result["student_profile"]["interests"]
    assert result["student_profile"]["region"] == "interior do Ceará"


def test_extract_topics():
    fake_response = MagicMock()
    fake_response.content = json.dumps({"topics": ["Fractions", "Percentages"]})

    state = {"syllabus_text": "1. Fractions\n2. Percentages"}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = extract_topics_node(state)

    assert result["topics"] == ["Fractions", "Percentages"]
    assert result["topics_source"] == "syllabus_provided"


def test_extract_topics_handles_list_content_response():
    """
    Some model versions (observed with Gemini 3.6 Flash in production)
    return `.content` as a list of content blocks instead of a plain
    string. This test locks in that _parse_json_response handles both
    shapes -- this is a real bug that surfaced live, not a hypothetical.
    """
    fake_response = MagicMock()
    fake_response.content = [
        {"type": "text", "text": json.dumps({"topics": ["Fractions", "Percentages"]})}
    ]

    state = {"syllabus_text": "1. Fractions\n2. Percentages"}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = extract_topics_node(state)

    assert result["topics"] == ["Fractions", "Percentages"]


def test_extract_topics_without_syllabus_uses_free_form_goal():
    """
    When the student has no syllabus (only a vague goal), the node
    should use the general suggestion path, and mark this in
    topics_source -- so the rest of the pipeline (validate, respond)
    handles it with extra care and transparency.
    """
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {"topics": ["Basic operations", "Fractions", "Percentages"]}
    )

    state = {"syllabus_text": None, "free_form_goal": "I want to learn basic math"}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = extract_topics_node(state)

    assert len(result["topics"]) == 3
    assert result["topics_source"] == "general_suggestion"


def test_build_schedule_generates_events_for_each_interval():
    state = {"topics": ["Fractions"], "start_date": "2026-09-01"}
    result = build_schedule_node(state)

    events = result["calendar_events"]
    assert len(events) == len(REVIEW_INTERVALS)
    assert all(ev["topic"] == "Fractions" for ev in events)
    # Dates must be in increasing order.
    dates = [ev["date"] for ev in events]
    assert dates == sorted(dates)


def test_build_schedule_generates_valid_ics():
    state = {"topics": ["Fractions", "Percentages"], "start_date": "2026-09-01"}
    result = build_schedule_node(state)

    ics = result["ics_content"]
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.strip().endswith("END:VCALENDAR")
    assert ics.count("BEGIN:VEVENT") == 2 * len(REVIEW_INTERVALS)
    assert "Fractions" in ics
    assert "Percentages" in ics


def test_build_schedule_spaces_topics_further_apart_for_light_pace():
    """
    A student with little daily time (study_pace "light") should get
    more days between the start of each topic than a student with an
    "intensive" pace -- this is what makes study_pace a real behavior
    change, not just a label stored and ignored.
    """
    base_state = {"topics": ["Fractions", "Percentages", "Geometry"], "start_date": "2026-09-01"}

    light_state = {**base_state, "student_profile": {"study_pace": "light"}}
    intensive_state = {**base_state, "student_profile": {"study_pace": "intensive"}}

    light_result = build_schedule_node(light_state)
    intensive_result = build_schedule_node(intensive_state)

    def first_exposure_date(events, topic):
        return next(
            ev["date"] for ev in events if ev["topic"] == topic and ev["review_type"] == "first_exposure"
        )

    light_gap = first_exposure_date(
        light_result["calendar_events"], "Percentages"
    ) 
    intensive_gap = first_exposure_date(
        intensive_result["calendar_events"], "Percentages"
    )

    # "Percentages" (the second topic) should start later in the light
    # pace schedule than in the intensive one.
    assert light_gap > intensive_gap
    assert TOPIC_SPACING_DAYS["light"] > TOPIC_SPACING_DAYS["intensive"]


def test_generate_flashcards_uses_fewer_cards_for_light_pace():
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {"flashcards": [{"topic": "Fractions", "front": "f1", "back": "b1", "difficulty": "easy"}]}
    )

    state = {
        "topics": ["Fractions"],
        "student_profile": {
            "works": "yes, full time",
            "interests": [],
            "region": "rural area",
            "study_pace": "light",
            "free_context": "",
        },
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        generate_flashcards_node(state)
        # Confirm the prompt sent to the LLM asked for the "light" card
        # count, not the default -- this is what proves the pace
        # actually changes behavior, not just gets stored unused.
        prompt_sent = mock_llm.return_value.invoke.call_args[0][0]

    assert f"Create {CARDS_PER_TOPIC['light']} study flashcards" in prompt_sent
    # Concrete counts -- raised so that, after the veracity filter in
    # respond_node may drop flagged cards, the student is still left with
    # enough real material per topic.
    assert CARDS_PER_TOPIC == {"light": 3, "moderate": 4, "intensive": 5}
    assert CARDS_PER_TOPIC["light"] < CARDS_PER_TOPIC["moderate"] < CARDS_PER_TOPIC["intensive"]


def test_generate_flashcards_contextualizes_with_interests():
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {
            "flashcards": [
                {
                    "topic": "Fractions",
                    "front": "What is 1/2?",
                    "back": "Half of something, like splitting a soccer match into two halves.",
                    "difficulty": "easy",
                }
            ]
        }
    )

    state = {
        "topics": ["Fractions"],
        "student_profile": {
            "works": "no",
            "interests": ["soccer"],
            "region": "Bahia",
            "free_context": "",
        },
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = generate_flashcards_node(state)

    assert len(result["flashcards"]) == 1
    assert "soccer" in result["flashcards"][0]["back"]


def test_generate_flashcards_prompt_includes_type_taxonomy():
    """
    The prompt sent to the model must describe the 5-type taxonomy and
    ask for a "type" field -- this is what makes the taxonomy an actual
    generation instruction, not just a schema the code hopes for.
    """
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {"flashcards": [{"topic": "Fractions", "type": "CONCEPT", "front": "f", "back": "b", "difficulty": "easy"}]}
    )

    state = {
        "topics": ["Fractions"],
        "student_profile": {"works": "no", "interests": [], "region": "Bahia", "free_context": ""},
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        generate_flashcards_node(state)
        prompt_sent = mock_llm.return_value.invoke.call_args[0][0]

    for card_type in CARD_TYPES:
        assert card_type in prompt_sent


def test_generate_flashcards_preserves_valid_type():
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {"flashcards": [{"topic": "Fractions", "type": "PITFALL", "front": "f", "back": "b", "difficulty": "easy"}]}
    )

    state = {
        "topics": ["Fractions"],
        "student_profile": {"works": "no", "interests": [], "region": "Bahia", "free_context": ""},
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = generate_flashcards_node(state)

    assert result["flashcards"][0]["type"] == "PITFALL"


def test_generate_flashcards_defaults_invalid_type_to_qa():
    """
    If the model returns a type outside the taxonomy (or omits it),
    the code must not propagate bad data silently -- it falls back to
    "QA" so downstream code (HTML rendering, Streamlit) never has to
    handle a missing/invalid type.
    """
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {"flashcards": [
            {"topic": "Fractions", "type": "NOT_A_REAL_TYPE", "front": "f1", "back": "b1", "difficulty": "easy"},
            {"topic": "Fractions", "front": "f2", "back": "b2", "difficulty": "easy"},  # type omitted entirely
        ]}
    )

    state = {
        "topics": ["Fractions"],
        "student_profile": {"works": "no", "interests": [], "region": "Bahia", "free_context": ""},
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = generate_flashcards_node(state)

    assert result["flashcards"][0]["type"] == "QA"
    assert result["flashcards"][1]["type"] == "QA"


def test_validate_detects_out_of_order_schedule():
    fake_response = MagicMock()
    fake_response.content = json.dumps({"issues": []})

    state = {
        "flashcards": [],
        "calendar_events": [
            {"topic": "Fractions", "date": "2026-09-10", "review_type": "first_exposure"},
            {"topic": "Fractions", "date": "2026-09-01", "review_type": "review_1"},  # out of order
        ],
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = validate_node(state)

    assert result["approved"] is False
    assert any(p["issue_type"] == "invalid_schedule" for p in result["issues_found"])


def test_validate_detects_invalid_card_type():
    """
    Deterministic safety net: even though generate_flashcards_node
    already defaults bad types to "QA", validate_node double-checks
    this independently -- so a future change that removes that
    fallback would still be caught here, not silently shipped.
    """
    fake_response = MagicMock()
    fake_response.content = json.dumps({"issues": []})

    state = {
        "flashcards": [
            {"topic": "Fractions", "type": "NOT_A_REAL_TYPE", "front": "f", "back": "b", "difficulty": "easy"}
        ],
        "calendar_events": [],
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = validate_node(state)

    assert result["approved"] is False
    assert any(p["issue_type"] == "invalid_card_type" for p in result["issues_found"])


def test_validate_accepts_all_valid_card_types():
    fake_response = MagicMock()
    fake_response.content = json.dumps({"issues": []})

    state = {
        "flashcards": [
            {"topic": "T", "type": t, "front": "f", "back": "b", "difficulty": "easy"}
            for t in ALLOWED_CARD_TYPES
        ],
        "calendar_events": [],
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = validate_node(state)

    assert result["approved"] is True


def test_respond_generates_html_with_flashcards():
    state = {
        "flashcards": [
            {"topic": "Fractions", "front": "1/2 = ?", "back": "Half", "difficulty": "easy"}
        ],
        "topics": ["Fractions"],
        "calendar_events": [{"topic": "Fractions", "date": "2026-09-01", "review_type": "x"}],
        "approved": True,
        "issues_found": [],
    }

    result = respond_node(state)

    assert result["flashcards_html"].startswith("<!DOCTYPE html>")
    assert "1/2 = ?" in result["flashcards_html"]
    assert "Half" in result["flashcards_html"]
    assert "personalized" in result["final_summary"]


# ---------------------------------------------------------------------
# Topic explanations ("study guide" intro shown before the flashcards)
# ---------------------------------------------------------------------

def _profile(**over):
    base = {"works": "no", "interests": [], "region": "Bahia",
            "study_pace": "moderate", "free_context": ""}
    base.update(over)
    return base


def test_generate_flashcards_generates_topic_explanations():
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {
            "topic_explanations": {
                "Fractions": "A fraction is a part of a whole, written as numerator over denominator.",
                "Percentages": "A percentage is a fraction out of 100.",
            },
            "flashcards": [
                {"topic": "Fractions", "type": "QA", "front": "f", "back": "b", "difficulty": "easy"}
            ],
        }
    )

    state = {"topics": ["Fractions", "Percentages"], "student_profile": _profile()}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = generate_flashcards_node(state)

    assert set(result["topic_explanations"]) == {"Fractions", "Percentages"}
    assert "part of a whole" in result["topic_explanations"]["Fractions"]
    assert result["topic_explanations"]["Percentages"] == "A percentage is a fraction out of 100."


def test_generate_flashcards_topic_explanations_default_empty_when_missing():
    """A model that omits topic_explanations must still yield one entry per
    topic (empty string), so downstream code never hits a missing key."""
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {"flashcards": [{"topic": "Fractions", "type": "QA", "front": "f", "back": "b", "difficulty": "easy"}]}
    )

    state = {"topics": ["Fractions", "Percentages"], "student_profile": _profile()}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = generate_flashcards_node(state)

    assert result["topic_explanations"] == {"Fractions": "", "Percentages": ""}


def test_generate_flashcards_prompt_asks_for_topic_overview():
    fake_response = MagicMock()
    fake_response.content = json.dumps({"topic_explanations": {}, "flashcards": []})

    state = {"topics": ["Fractions"], "student_profile": _profile()}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        generate_flashcards_node(state)
        prompt_sent = mock_llm.return_value.invoke.call_args[0][0]

    assert "topic_explanations" in prompt_sent
    assert "overview" in prompt_sent.lower()


# ---------------------------------------------------------------------
# used_interest: which personal interest each card leaned on
# ---------------------------------------------------------------------

def test_generate_flashcards_captures_used_interest_when_it_matches_the_profile():
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {
            "flashcards": [
                {"topic": "Fractions", "type": "USE_CASE", "front": "f1", "back": "b1",
                 "difficulty": "easy", "used_interest": "soccer"},
                {"topic": "Fractions", "type": "QA", "front": "f2", "back": "b2",
                 "difficulty": "easy", "used_interest": ""},
            ]
        }
    )
    state = {"topics": ["Fractions"], "student_profile": _profile(interests=["soccer", "barbecue"])}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = generate_flashcards_node(state)

    assert result["flashcards"][0]["used_interest"] == "soccer"
    assert result["flashcards"][1]["used_interest"] == ""


def test_generate_flashcards_used_interest_defaults_to_empty_when_key_missing():
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {"flashcards": [{"topic": "Fractions", "type": "QA", "front": "f", "back": "b", "difficulty": "easy"}]}
    )
    state = {"topics": ["Fractions"], "student_profile": _profile(interests=["soccer"])}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = generate_flashcards_node(state)

    assert result["flashcards"][0]["used_interest"] == ""


def test_generate_flashcards_drops_used_interest_not_in_profile():
    """The model can name an interest the student never gave -- only interests
    actually in the profile are kept, so the 'personalized using' tag stays honest."""
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {"flashcards": [{"topic": "Fractions", "type": "USE_CASE", "front": "f", "back": "b",
                         "difficulty": "easy", "used_interest": "astronomy"}]}
    )
    state = {"topics": ["Fractions"], "student_profile": _profile(interests=["soccer"])}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = generate_flashcards_node(state)

    assert result["flashcards"][0]["used_interest"] == ""


def test_generate_flashcards_prompt_asks_for_used_interest():
    fake_response = MagicMock()
    fake_response.content = json.dumps({"flashcards": []})
    state = {"topics": ["Fractions"], "student_profile": _profile(interests=["soccer"])}

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        generate_flashcards_node(state)
        prompt_sent = mock_llm.return_value.invoke.call_args[0][0]

    assert "used_interest" in prompt_sent


# ---------------------------------------------------------------------
# Verification: pin each issue to a card, and withhold unfixed cards
# ---------------------------------------------------------------------

def test_validate_asks_which_card_and_normalizes_affected_card_front():
    fake_response = MagicMock()
    fake_response.content = json.dumps(
        {
            "issues": [
                {"issue_type": "conceptual_error", "description": "d", "affected_excerpt": "e",
                 "affected_card_front": "  the exact front  ", "affected_topic": "  T  "},
                {"issue_type": "forced_contextualization", "description": "d2", "affected_excerpt": "e2"},
            ]
        }
    )

    state = {
        "flashcards": [
            {"topic": "T", "type": "QA", "front": "the exact front", "back": "b", "difficulty": "easy"}
        ],
        "calendar_events": [],
    }

    with patch("app.graph.nodes._llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = fake_response
        result = validate_node(state)
        prompt_sent = mock_llm.return_value.invoke.call_args[0][0]

    assert "affected_card_front" in prompt_sent
    assert "affected_topic" in prompt_sent
    issues = result["issues_found"]
    assert issues[0]["affected_card_front"] == "the exact front"  # stripped
    assert issues[0]["affected_topic"] == "T"  # stripped
    assert issues[1]["affected_card_front"] == ""  # defaulted when the model omits it
    assert issues[1]["affected_topic"] == ""  # defaulted when the model omits it


def test_respond_removes_flashcard_with_unresolved_content_issue():
    state = {
        "flashcards": [
            {"topic": "Ratios", "type": "QA", "front": "good A", "back": "ba", "difficulty": "easy"},
            {"topic": "Ratios", "type": "USE_CASE", "front": "bad musicians analogy", "back": "wrong", "difficulty": "easy"},
            {"topic": "Ratios", "type": "SUMMARY", "front": "good C", "back": "bc", "difficulty": "easy"},
        ],
        "topics": ["Ratios"],
        "calendar_events": [{"topic": "Ratios", "date": "2026-09-01", "review_type": "x"}],
        "approved": False,
        "issues_found": [
            {"issue_type": "forced_contextualization", "description": "backwards analogy",
             "affected_excerpt": "musicians", "affected_card_front": "bad musicians analogy",
             "affected_topic": "Ratios"},
        ],
    }

    result = respond_node(state)

    fronts = [fc["front"] for fc in result["flashcards"]]
    assert "bad musicians analogy" not in fronts
    # affected_card_front matched a real card, so ONLY that card goes -- the
    # affected_topic is ignored, the topic's other verified cards stay.
    assert "good A" in fronts and "good C" in fronts
    assert [fc["front"] for fc in result["removed_flashcards"]] == ["bad musicians analogy"]
    assert "bad musicians analogy" not in result["flashcards_html"]
    assert "good A" in result["flashcards_html"]


def test_respond_keeps_all_cards_when_approved():
    state = {
        "flashcards": [
            {"topic": "Ratios", "type": "QA", "front": "card X", "back": "b", "difficulty": "easy"}
        ],
        "topics": ["Ratios"],
        "calendar_events": [],
        "approved": True,
        "issues_found": [
            {"issue_type": "forced_contextualization", "description": "d",
             "affected_excerpt": "e", "affected_card_front": "card X"},
        ],
    }

    result = respond_node(state)

    assert [fc["front"] for fc in result["flashcards"]] == ["card X"]
    assert result["removed_flashcards"] == []


def test_respond_withholds_whole_topic_when_issue_names_topic_but_not_card():
    """A content issue the reviewer could not pin to one card, but that
    does name a topic -> every card of that topic is withheld (not just an
    ambiguously-matched one), and other topics are untouched."""
    state = {
        "flashcards": [
            {"topic": "Ratios", "type": "QA", "front": "r1", "back": "b", "difficulty": "easy"},
            {"topic": "Ratios", "type": "USE_CASE", "front": "r2", "back": "b", "difficulty": "easy"},
            {"topic": "Fractions", "type": "QA", "front": "f1", "back": "b", "difficulty": "easy"},
        ],
        "topics": ["Ratios", "Fractions"],
        "calendar_events": [],
        "approved": False,
        "issues_found": [
            {"issue_type": "forced_contextualization",
             "description": "an analogy in the ratios cards is off; cannot pin the exact card",
             "affected_excerpt": "", "affected_card_front": "", "affected_topic": "Ratios"},
        ],
    }

    result = respond_node(state)

    by_topic = {}
    for fc in result["flashcards"]:
        by_topic.setdefault(fc["topic"], []).append(fc)

    assert len(by_topic["Ratios"]) == 1  # both real cards gone, one placeholder
    assert by_topic["Ratios"][0]["type"] == "SUMMARY"
    assert "withheld" in by_topic["Ratios"][0]["back"]
    assert [fc["front"] for fc in by_topic["Fractions"]] == ["f1"]  # untouched
    assert sorted(fc["front"] for fc in result["removed_flashcards"]) == ["r1", "r2"]


def test_respond_withholds_all_topics_when_content_issue_has_no_anchor():
    """Worst case: a content issue with neither a usable affected_card_front
    nor an affected_topic. Nothing unverified may ship, so every topic that
    had cards is emptied and gets a conservative placeholder."""
    state = {
        "flashcards": [
            {"topic": "Ratios", "type": "QA", "front": "r1", "back": "b", "difficulty": "easy"},
            {"topic": "Fractions", "type": "QA", "front": "f1", "back": "b", "difficulty": "easy"},
        ],
        "topics": ["Ratios", "Fractions"],
        "calendar_events": [],
        "approved": False,
        "issues_found": [
            {"issue_type": "conceptual_error", "description": "something is wrong somewhere",
             "affected_excerpt": "", "affected_card_front": "", "affected_topic": ""},
        ],
    }

    result = respond_node(state)

    assert sorted(fc["type"] for fc in result["flashcards"]) == ["SUMMARY", "SUMMARY"]
    assert sorted(fc["front"] for fc in result["flashcards"]) == [
        "Review needed: Fractions",
        "Review needed: Ratios",
    ]
    assert sorted(fc["front"] for fc in result["removed_flashcards"]) == ["f1", "r1"]


def test_respond_adds_fallback_when_topic_loses_all_cards():
    state = {
        "flashcards": [
            {"topic": "Ratios", "type": "QA", "front": "only card, wrong", "back": "b", "difficulty": "easy"},
            {"topic": "Fractions", "type": "QA", "front": "fine card", "back": "b", "difficulty": "easy"},
        ],
        "topics": ["Ratios", "Fractions"],
        "calendar_events": [],
        "approved": False,
        "issues_found": [
            {"issue_type": "conceptual_error", "description": "wrong",
             "affected_excerpt": "x", "affected_card_front": "only card, wrong"},
        ],
    }

    result = respond_node(state)

    by_topic = {}
    for fc in result["flashcards"]:
        by_topic.setdefault(fc["topic"], []).append(fc)

    assert list(by_topic["Ratios"]) and len(by_topic["Ratios"]) == 1
    fallback = by_topic["Ratios"][0]
    assert fallback["type"] == "SUMMARY"
    assert "withheld" in fallback["back"]
    assert [fc["front"] for fc in by_topic["Fractions"]] == ["fine card"]
    assert [fc["front"] for fc in result["removed_flashcards"]] == ["only card, wrong"]
