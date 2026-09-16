"""
Agent nodes, and the comparison baseline required by the challenge.

BASELINE: a single prompt asking for "schedule + flashcards" at once,
with no student profile, no real spaced repetition science, no real
calendar file -- represents the most obvious, simplest way to try to
solve this.

AGENT SOLUTION: a 6-node pipeline, with two central capabilities:
- Context: the student profile carried through the whole pipeline, used
  to contextualize flashcards (a practical application of Paulo Freire's
  idea of teaching from the student's own context).
- Verification: reviews flashcards and schedule before delivering.
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List
from uuid import uuid4

from langchain_google_genai import ChatGoogleGenerativeAI

from app.graph.state import (
    AgentState,
    ReviewEvent,
    Flashcard,
    StudentProfile,
    TYPE_ICONS,
    ValidationIssue,
)

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.5-flash-lite")

# ---------------------------------------------------------------------
# Tuning constants -- grouped here so every knob the pipeline exposes is
# visible in one place, not scattered between the node functions that
# happen to use them.
# ---------------------------------------------------------------------

# Maximum number of times generate_flashcards_node is retried after a
# failed validation, before the graph gives up and proceeds to respond
# anyway (respond_node then withholds any card still flagged). Prevents an
# infinite loop if the model keeps making the same kind of mistake.
MAX_FLASHCARD_RETRIES = 3

# Spaced repetition intervals, in days after first exposure to the topic,
# based on the Ebbinghaus forgetting curve: reviewing content at growing
# intervals reduces forgetting over time.
REVIEW_INTERVALS = [
    (0, "first_exposure"),
    (1, "review_1"),
    (3, "review_2"),
    (7, "review_3"),
    (14, "review_4"),
]

# Days between the start of consecutive topics, based on the student's
# realistic daily study time -- a "light" pace spaces topics out more,
# so review load doesn't stack up faster than the student can keep up
# with; an "intensive" pace can start topics closer together.
TOPIC_SPACING_DAYS = {"light": 4, "moderate": 2, "intensive": 1}

# Flashcards per topic, based on the student's realistic daily study
# time -- fewer, more essential cards for a "light" pace instead of
# overloading a student who has little time to review; more for
# "intensive", since they have room for deeper coverage per topic.
# Deliberately generous: the veracity filter in respond_node can drop
# flagged cards, so a low count could leave a topic thin.
CARDS_PER_TOPIC = {"light": 3, "moderate": 4, "intensive": 5}

# Flashcard taxonomy: each card is tagged with one of these types, so
# a student's review mix isn't just "question -> answer" repeated --
# different types exercise different depths of understanding.
CARD_TYPES = {
    "CONCEPT": "Explains the topic/module concept, adapted and personalized to the student's routine, context and interests (e.g. soccer, farming, etc.)",
    "USE_CASE": "A practical, real-world or professional example of applying the concept",
    "PITFALL": "A common mistake or misconception when learning this, plus a practical tip to avoid/remember it",
    "QA": "A traditional direct question (front) and detailed answer (back)",
    "SUMMARY": "A fast key-points summary of the topic, for accelerated spaced-repetition review",
}
ALLOWED_CARD_TYPES = set(CARD_TYPES.keys())


def _llm():
    return ChatGoogleGenerativeAI(model=MODEL_NAME, temperature=0)


_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _parse_json_response(raw) -> dict:
    """
    Parses the model's JSON response. Newer Gemini models sometimes
    return `.content` as a list of content blocks (e.g.
    [{"type": "text", "text": "..."}]) instead of a plain string --
    this normalizes either shape before parsing.

    On a JSONDecodeError it makes ONE defensive repair-and-retry pass:
    small models, on long payloads, occasionally emit a trailing comma
    before a closing `}` or `]` (the exact shape that crashed a live
    `evaluate.py` run). The repair is intentionally narrow -- if the
    second parse still fails (e.g. a genuinely truncated object), the
    error propagates instead of being masked.
    """
    if isinstance(raw, list):
        raw = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw
        )
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(_TRAILING_COMMA_RE.sub(r"\1", raw))


# ---------------------------------------------------------------------
# BASELINE
# ---------------------------------------------------------------------

def generate_baseline_path(syllabus_text: str) -> str:
    """
    Baseline required by the challenge: a single direct prompt, no
    student profile, no real spaced repetition science, no real
    calendar file generated -- just loose text.
    """
    llm = _llm()
    prompt = (
        f"Based on this course syllabus, create a study schedule and "
        f"some review flashcards:\n\n{syllabus_text}"
    )
    response = llm.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return content


# ---------------------------------------------------------------------
# AGENT SOLUTION
# ---------------------------------------------------------------------

def parse_profile_node(state: AgentState) -> dict:
    """
    Turns the student's free-text questionnaire answers into a
    structured profile -- this profile is carried through the rest of
    the pipeline and used to contextualize the flashcards, AND to pace
    the schedule and flashcard load realistically.

    study_pace is deliberately part of the profile, not an afterthought:
    Freire's idea of teaching from the student's real context isn't just
    about using their interests as examples -- it also means respecting
    that a working student has less daily study time than one who
    doesn't work, and the plan should reflect that, not assume everyone
    has equal free time.
    """
    llm = _llm()
    prompt = f"""Extract a structured profile from a student's questionnaire
answers. Classify their realistic daily study time into one of exactly
three categories: "light" (roughly under 30 min/day -- e.g. works full
time, little free time), "moderate" (roughly 30-90 min/day), or
"intensive" (90+ min/day -- e.g. doesn't work, studies full time). If
the answers don't mention available time at all, default to "moderate".

Respond ONLY with JSON in this format:
{{"works": "...", "interests": ["...", "..."], "region": "...", "study_pace": "light|moderate|intensive", "free_context": "..."}}

Questionnaire answers:
{state['questionnaire_answers']}
"""
    response = llm.invoke(prompt)
    parsed = _parse_json_response(response.content)

    study_pace = parsed.get("study_pace", "moderate")
    if study_pace not in ("light", "moderate", "intensive"):
        study_pace = "moderate"  # safe default if the model returns something unexpected

    profile: StudentProfile = {
        "works": parsed.get("works", "not informed"),
        "interests": parsed.get("interests", []),
        "region": parsed.get("region", "not informed"),
        "study_pace": study_pace,
        "free_context": parsed.get("free_context", ""),
    }
    return {"student_profile": profile}


def extract_topics_node(state: AgentState) -> dict:
    """
    Extracts the list of study topics in one of two ways:

    1. If the student has a syllabus/curriculum (main path, more
       reliable): extract topics from the real text, pasted by the
       student -- the agent does not fetch the syllabus itself, to
       avoid depending on internet/scraping during execution.

    2. If the student does NOT have a defined syllabus and only knows a
       vague goal ("I want to learn X"): the model suggests a reasonable
       topic breakdown, using general knowledge. This path is clearly
       less reliable than the first (the model is "guessing" a
       curriculum structure, not reading a real one) -- so the
       `topics_source` field marks the origin, for transparency with the
       student and so the validate_node can be stricter in this case.
    """
    llm = _llm()
    syllabus = state.get("syllabus_text")

    if syllabus and syllabus.strip():
        prompt = f"""Extract the main list of study topics from this course
syllabus, in the order they appear. Respond ONLY with JSON in this
format: {{"topics": ["topic 1", "topic 2", ...]}}

Syllabus:
{syllabus}
"""
        source = "syllabus_provided"
    else:
        goal = state.get("free_form_goal", "")
        prompt = f"""The student does not have a defined syllabus/curriculum,
only a study goal. Suggest a reasonable topic breakdown, from most
basic to most advanced, for someone starting from scratch on this
subject. Be conservative: prefer widely recognized, well-established
topics, avoid very niche or uncertain ones, since you are inferring
the structure, not reading a real curriculum.

Student's goal: {goal}

Respond ONLY with JSON in this format:
{{"topics": ["topic 1", "topic 2", ...]}}
"""
        source = "general_suggestion"

    response = llm.invoke(prompt)
    parsed = _parse_json_response(response.content)
    return {"topics": parsed.get("topics", []), "topics_source": source}


def build_schedule_node(state: AgentState) -> dict:
    """
    Applies spaced repetition intervals to each topic, starting from the
    given start date, and generates an .ics file (universal calendar
    format) -- importable into Google Calendar, Outlook, Apple Calendar,
    with no API/OAuth needed, and works offline once imported.

    The spacing between topics is adjusted by the student's study_pace
    (from their profile) -- this is what turns "personalization" from
    just flashcard flavor text into something that actually changes the
    plan's realism: a student with little daily time gets a schedule
    that doesn't pile up more review sessions per day than they can
    realistically do.
    """
    start_date = datetime.strptime(state["start_date"], "%Y-%m-%d")
    study_pace = state.get("student_profile", {}).get("study_pace", "moderate")
    spacing_days = TOPIC_SPACING_DAYS.get(study_pace, TOPIC_SPACING_DAYS["moderate"])

    events: List[ReviewEvent] = []

    for i, topic in enumerate(state["topics"]):
        # Each topic starts `spacing_days` after the previous one, so
        # topics don't all pile up on the same day -- and pile up less
        # for students with less daily study time available.
        topic_start = start_date + timedelta(days=i * spacing_days)
        for day_offset, review_type in REVIEW_INTERVALS:
            event_date = topic_start + timedelta(days=day_offset)
            events.append(
                ReviewEvent(
                    topic=topic,
                    date=event_date.strftime("%Y-%m-%d"),
                    review_type=review_type,
                )
            )

    ics_content = _build_ics(events)
    return {"calendar_events": events, "ics_content": ics_content}


def _build_ics(events: List[ReviewEvent]) -> str:
    """
    Builds an .ics file by hand (RFC 5545 format, plain text) -- no
    external library, no calendar API call needed.
    """
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//offline-study-bridge//EN"]

    for event in events:
        date_str = event["date"].replace("-", "")
        readable_type = event["review_type"].replace("_", " ").title()
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uuid4()}@offline-study-bridge",
                f"DTSTART;VALUE=DATE:{date_str}",
                f"DTEND;VALUE=DATE:{date_str}",
                f"SUMMARY:Study: {event['topic']} ({readable_type})",
                f"DESCRIPTION:{readable_type} session for topic '{event['topic']}', "
                f"part of the spaced repetition study path.",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def generate_flashcards_node(state: AgentState) -> dict:
    """
    Generates flashcards per topic, contextualized with the student's
    interests -- a practical application of Paulo Freire's idea of
    teaching from the student's context and reality, instead of generic,
    decontextualized examples.

    The number of cards per topic is also adapted to study_pace: context
    isn't only about examples that resonate with the student, it's also
    about respecting how much time they realistically have -- a student
    with 20 minutes a day is set up to fail by the same card load as one
    who studies full time.

    If this is a retry (state["retry_count"] > 0, meaning a previous
    attempt failed validation), the prompt includes the specific issues
    found last time, asking the model to explicitly avoid repeating them
    -- this is what turns validate_node from a passive reporter into an
    active part of a self-correcting loop.
    """
    llm = _llm()
    profile = state["student_profile"]
    interests = ", ".join(profile["interests"]) or "no specific interests informed"
    study_pace = profile.get("study_pace", "moderate")
    num_cards = CARDS_PER_TOPIC.get(study_pace, CARDS_PER_TOPIC["moderate"])

    retry_feedback = ""
    previous_issues = state.get("issues_found")
    if previous_issues:
        issues_text = "\n".join(
            f"- [{issue['issue_type']}] {issue['description']}"
            for issue in previous_issues
        )
        retry_feedback = f"""
IMPORTANT: A previous attempt at these flashcards had the following
problems, found during review. Generate NEW flashcards that specifically
avoid repeating these exact mistakes:
{issues_text}
"""

    types_description = "\n".join(f"- {t}: {desc}" for t, desc in CARD_TYPES.items())

    prompt = f"""Create {num_cards} study flashcards for EACH of these topics:
{state['topics']}

The student has these interests: {interests}
Region: {profile['region']}
Daily study time available: {study_pace} (light = under 30 min/day, moderate = 30-90 min/day, intensive = 90+ min/day)
Context: {profile['free_context']}

Each flashcard must be tagged with a "type", chosen from this taxonomy:
{types_description}

For each topic, choose a USEFUL MIX of types within the {num_cards}-card
budget -- don't force all 5 types into every topic if the budget is
small; prioritize whichever types teach that specific topic best. QA is
a safe default to fall back on, but variety is preferred when the
budget allows for it.

Whenever it makes pedagogical sense, use examples tied to the student's
interests to make the concept more concrete -- but NEVER force an
analogy that hurts clarity. If a topic has no natural connection to the
interests, use a clear generic example instead of a forced analogy.
If daily study time is "light", prioritize the {num_cards} most
essential points per topic instead of trying to cover everything.

For every flashcard whose example or analogy is built on one of the
student's personal interests, set "used_interest" to that interest,
copied from the interests list above. Set "used_interest" to "" for
cards that use a generic example or no example -- that is expected and
fine for many cards.

Also write a short plain-language overview for EACH topic: 3-5 sentences
that introduce the topic BEFORE the student starts practicing with the
flashcards. This overview is separate from the flashcards and separate
from any CONCEPT card -- it is a fixed introduction that comes first.
Keep it factual and conservative; do not force interest-based analogies
into the overview.
{retry_feedback}
Respond ONLY with JSON in this format:
{{"topic_explanations": {{"<topic>": "<3-5 sentence overview>"}}, "flashcards": [{{"topic": "...", "type": "CONCEPT|USE_CASE|PITFALL|QA|SUMMARY", "front": "...", "back": "...", "difficulty": "easy", "used_interest": ""}}]}}
"""
    response = llm.invoke(prompt)
    parsed = _parse_json_response(response.content)
    raw_flashcards = parsed.get("flashcards", [])

    # A card may only claim an interest that is actually in the profile --
    # keeps the "personalized using: ..." tag honest if the model invents one.
    profile_interests = [i.strip() for i in profile["interests"] if i.strip()]

    def _match_interest(raw: str) -> str:
        raw = str(raw or "").strip()
        if not raw:
            return ""
        low = raw.lower()
        for interest in profile_interests:
            il = interest.lower()
            if low == il or low in il or il in low:
                return raw
        return ""

    # Defensive default: if the model omits "type" or returns something
    # outside the taxonomy, fall back to "QA" rather than let bad data
    # propagate silently -- validate_node also double-checks this
    # deterministically, but failing safe here means downstream code
    # (HTML rendering, Streamlit) never has to handle a missing key.
    flashcards: List[Flashcard] = []
    for fc in raw_flashcards:
        card_type = fc.get("type", "QA")
        if card_type not in ALLOWED_CARD_TYPES:
            card_type = "QA"
        flashcards.append(
            Flashcard(
                topic=fc.get("topic", ""),
                type=card_type,
                front=fc.get("front", ""),
                back=fc.get("back", ""),
                difficulty=fc.get("difficulty", "medium"),
                used_interest=_match_interest(fc.get("used_interest", "")),
            )
        )

    # Per-topic overview shown before any flashcard. Normalized to one
    # entry per real topic so downstream code (respond_node, Streamlit)
    # can iterate state["topics"] and never hit a missing key.
    raw_explanations = parsed.get("topic_explanations", {})
    if not isinstance(raw_explanations, dict):
        raw_explanations = {}
    topic_explanations = {
        topic: str(raw_explanations.get(topic, "")).strip()
        for topic in state["topics"]
    }

    return {"flashcards": flashcards, "topic_explanations": topic_explanations}


def validate_node(state: AgentState) -> dict:
    """
    Verification: reviews flashcards for conceptual errors and forced
    contextualization (an analogy that confuses more than it helps), and
    checks that the schedule dates are in increasing order.

    retry_count tracks how many generation attempts have now failed
    validation (starts at 0, becomes 1 after the first failed attempt,
    2 after the second, etc.). MAX_FLASHCARD_RETRIES caps the TOTAL
    number of generate_flashcards attempts (not additional retries on
    top of the first) -- with MAX_FLASHCARD_RETRIES=3, at most 3
    generate_flashcards calls happen before the graph gives up and
    proceeds to respond regardless.

    When topics came from a general suggestion (student had no
    syllabus, topics_source == "general_suggestion"), the review asks
    for extra rigor explicitly -- the risk of error is higher because
    the model inferred the curriculum structure instead of reading a
    real one.
    """
    llm = _llm()

    flashcards_text = "\n".join(
        f"- [{fc.get('topic', '')}] {fc.get('front', '')} -> {fc.get('back', '')}"
        for fc in state["flashcards"]
    )

    topics_source = state.get("topics_source", "syllabus_provided")
    strictness_note = ""
    if topics_source == "general_suggestion":
        strictness_note = (
            "\nATTENTION: these topics were SUGGESTED by the model (the "
            "student had no real syllabus), so be extra strict -- be "
            "suspicious of very specific or niche claims, which are more "
            "likely to be wrong when the curriculum structure was inferred.\n"
        )

    prompt = f"""Review these study flashcards. Point out:
1. Conceptual errors
2. Forced contextualization (analogies that confuse more than they help)
{strictness_note}
For every issue, identify WHICH flashcard it is about by copying that
card's exact "front" text into "affected_card_front", and put the card's
topic (the text shown in [brackets]) in "affected_topic". Always fill in
"affected_topic". Leave "affected_card_front" empty only if the issue
genuinely is not about one specific card.

Flashcards:
{flashcards_text}

Respond ONLY with JSON in this format:
{{"issues": [{{"issue_type": "conceptual_error", "description": "...", "affected_excerpt": "...", "affected_card_front": "...", "affected_topic": "..."}}]}}
If there are no issues, respond {{"issues": []}}.
"""
    response = llm.invoke(prompt)
    parsed = _parse_json_response(response.content)
    issues: List[ValidationIssue] = [
        ValidationIssue(
            issue_type=it.get("issue_type", "conceptual_error"),
            description=it.get("description", ""),
            affected_excerpt=it.get("affected_excerpt", ""),
            affected_card_front=str(it.get("affected_card_front", "")).strip(),
            affected_topic=str(it.get("affected_topic", "")).strip(),
        )
        for it in parsed.get("issues", [])
        if isinstance(it, dict)
    ]

    # Deterministic check (no LLM) of the schedule: dates must be in
    # non-decreasing order within each topic.
    events_by_topic: Dict[str, List[str]] = {}
    for ev in state["calendar_events"]:
        events_by_topic.setdefault(ev["topic"], []).append(ev["date"])

    for topic, dates in events_by_topic.items():
        if dates != sorted(dates):
            issues.append(
                ValidationIssue(
                    issue_type="invalid_schedule",
                    description=f"Dates out of order for topic '{topic}'",
                    affected_excerpt=topic,
                    affected_card_front="",
                    affected_topic=topic,
                )
            )

    # Deterministic check (no LLM) that every flashcard's type is one of
    # the taxonomy's allowed values -- generate_flashcards_node already
    # defaults bad values to "QA", so this should never fire in
    # practice, but it's a cheap safety net against a future change
    # that removes that fallback.
    for fc in state.get("flashcards", []):
        if fc.get("type") not in ALLOWED_CARD_TYPES:
            issues.append(
                ValidationIssue(
                    issue_type="invalid_card_type",
                    description=f"Flashcard has an unrecognized type: {fc.get('type')!r}",
                    affected_excerpt=fc.get("front", ""),
                    affected_card_front=fc.get("front", ""),
                    affected_topic=fc.get("topic", ""),
                )
            )

    approved = len(issues) == 0
    retry_count = state.get("retry_count", 0)
    if not approved:
        retry_count += 1

    return {
        "issues_found": issues,
        "approved": approved,
        "retry_count": retry_count,
    }


# Text for the conservative placeholder used only when EVERY flashcard of
# a topic had to be withheld -- it makes no factual claim about the topic
# itself, it just states plainly that verified material is missing.
FALLBACK_CARD_BACK = (
    "The agent generated review material for this topic, but it did not "
    "pass automated verification and the self-correction retry could not "
    "fix it, so it was withheld rather than shown as reliable. Use a "
    "trusted reference (a textbook or official course material) for this "
    "topic."
)

# Issue types that mean the card CONTENT is wrong (as opposed to a
# structural problem like an out-of-order schedule). Only these cause a
# specific card to be pulled from the student's final set.
CONTENT_ISSUE_TYPES = ("conceptual_error", "forced_contextualization")


def _filter_unresolved_flashcards(state: AgentState):
    """
    Drops the flashcards that verification tied to an unfixed content
    problem after the retry loop gave up -- veracity over completeness: a
    wrong card is worse than a missing one.

    For each content issue (conceptual_error / forced_contextualization):
    - if it names an `affected_card_front` that matches a real card, only
      that card is dropped;
    - otherwise the issue could not be pinned to one card, so the WHOLE
      affected topic is dropped (its `affected_topic`, or -- as a last
      resort when even that is missing -- every topic that still has
      cards, since nothing unverified may ship).

    Topics with no issue at all are never touched. If a topic loses ALL
    of its cards, one conservative SUMMARY placeholder is added so it is
    never silently empty.

    Returns (kept_flashcards, removed_flashcards).
    """
    flashcards = list(state.get("flashcards", []))
    if state.get("approved", True):
        return flashcards, []

    content_issues = [
        iss for iss in state.get("issues_found", [])
        if iss.get("issue_type") in CONTENT_ISSUE_TYPES
    ]
    if not content_issues:
        return flashcards, []

    existing_fronts = {(fc.get("front") or "").strip() for fc in flashcards}
    all_topics = {
        (fc.get("topic") or "").strip()
        for fc in flashcards
        if (fc.get("topic") or "").strip()
    }

    bad_fronts, bad_topics = set(), set()
    for iss in content_issues:
        front = (iss.get("affected_card_front") or "").strip()
        if front and front in existing_fronts:
            bad_fronts.add(front)
            continue
        # Could not pin the issue to a specific existing card -> withhold
        # the whole affected topic instead of letting the card through.
        topic = (iss.get("affected_topic") or "").strip()
        if topic:
            bad_topics.add(topic)
        else:
            bad_topics |= all_topics

    if not bad_fronts and not bad_topics:
        return flashcards, []

    kept, removed = [], []
    for fc in flashcards:
        front = (fc.get("front") or "").strip()
        topic = (fc.get("topic") or "").strip()
        if front in bad_fronts or topic in bad_topics:
            removed.append(fc)
        else:
            kept.append(fc)

    if removed:
        topics_with_cards = {(fc.get("topic") or "").strip() for fc in kept}
        for topic in sorted({(fc.get("topic") or "").strip() for fc in removed}):
            if topic and topic not in topics_with_cards:
                kept.append(
                    Flashcard(
                        topic=topic,
                        type="SUMMARY",
                        front=f"Review needed: {topic}",
                        back=FALLBACK_CARD_BACK,
                        difficulty="easy",
                        used_interest="",
                    )
                )
                topics_with_cards.add(topic)

    return kept, removed


def respond_node(state: AgentState) -> dict:
    """
    Formats the flashcards into a single, self-contained HTML page,
    ready for offline use, and builds a final summary of the generated
    study path.

    Before formatting, it drops any flashcard that verification tied to
    an unfixed conceptual error or forced contextualization (see
    `_filter_unresolved_flashcards`) -- the student never sees flagged
    content presented as reliable. `issues_found` itself is left intact
    for technical review.
    """
    flashcards, removed_flashcards = _filter_unresolved_flashcards(state)

    explanations = state.get("topic_explanations", {}) or {}
    guide_items = "".join(
        f'<div class="guide-topic"><h3>{topic}</h3><p>{explanations.get(topic, "")}</p></div>'
        for topic in state.get("topics", [])
        if (explanations.get(topic) or "").strip()
    )
    guide_html = (
        f'<section class="study-guide"><h2>Study guide &mdash; read this first</h2>{guide_items}</section>'
        if guide_items
        else ""
    )

    cards_html = ""
    for fc in flashcards:
        card_type = fc.get("type", "QA")
        icon = TYPE_ICONS.get(card_type, "❓")
        cards_html += f"""
        <div class="card">
          <div class="topic">{icon} {card_type} · {fc.get('topic', '')} · {fc.get('difficulty', 'medium')}</div>
          <div class="front">{fc.get('front', '')}</div>
          <div class="back">{fc.get('back', '')}</div>
        </div>"""

    warning_html = ""
    if removed_flashcards:
        items = "".join(
            f"<li>[{p['issue_type']}] {p['description']}</li>"
            for p in state.get("issues_found", [])
            if p.get("issue_type") in CONTENT_ISSUE_TYPES
        )
        warning_html = (
            f'<div class="warning"><strong>⚠️ Note:</strong> {len(removed_flashcards)} '
            "flashcard(s) were removed from this set because automated verification "
            "found a problem the self-correction retry could not fix. They are "
            "withheld rather than shown as reliable. Technical detail:"
            f"<ul>{items}</ul></div>"
        )
    elif not state.get("approved", True):
        items = "".join(
            f"<li>[{p['issue_type']}] {p['description']}</li>"
            for p in state.get("issues_found", [])
        )
        warning_html = f'<div class="warning"><strong>⚠️ Attention:</strong> review pending:<ul>{items}</ul></div>'

    topics_source = state.get("topics_source", "syllabus_provided")
    source_note_html = ""
    if topics_source == "general_suggestion":
        source_note_html = (
            '<div class="source-note">ℹ️ <strong>Note:</strong> you did not provide a '
            "specific syllabus, so these topics were <strong>suggested</strong> "
            "by the agent based on your goal, not extracted from an official "
            "curriculum. Worth checking if they cover what you actually need "
            "to study.</div>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Flashcards - Personalized Study Path</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 800px; margin: 2rem auto;
         padding: 0 1rem; color: #222; }}
  h1 {{ color: #5B3A9E; }}
  .card {{ border: 2px solid #5B3A9E; border-radius: 10px; padding: 1rem 1.2rem;
           margin-bottom: 1rem; background: #faf8ff; }}
  .topic {{ font-size: 0.8rem; text-transform: uppercase; color: #5B3A9E;
             font-weight: bold; margin-bottom: 0.4rem; }}
  .front {{ font-weight: bold; margin-bottom: 0.5rem; }}
  .back {{ color: #444; }}
  .source-note {{ background: #e8f0fe; border: 1px solid #a8c7fa; border-radius: 6px;
                 padding: 0.8rem 1rem; margin-bottom: 1.2rem; font-size: 0.9rem; }}
  .warning {{ background: #fff3cd; border: 1px solid #ffe08a; border-radius: 6px;
            padding: 1rem; margin-top: 1.5rem; }}
  .study-guide {{ background: #f4f2fc; border: 1px solid #d9d2f2; border-radius: 10px;
                 padding: 0.6rem 1.2rem; margin-bottom: 1.5rem; }}
  .study-guide h2 {{ font-size: 1rem; color: #5B3A9E; margin: 0.5rem 0; }}
  .guide-topic h3 {{ font-size: 0.9rem; margin: 0.7rem 0 0.2rem 0; color: #3D2B7C; }}
  .guide-topic p {{ margin: 0 0 0.4rem 0; }}
  .cards {{ }}
  @media print {{
    @page {{ margin: 1cm; }}
    body {{ margin: 0; color: #000; max-width: none; }}
    h1, p {{ color: #000; }}
    .source-note, .warning {{ display: none !important; }}
    .study-guide {{ background: #fff !important; border: 1px solid #000; }}
    .study-guide h2, .guide-topic h3 {{ color: #000 !important; }}
    .cards {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.5cm; }}
    .card {{
      border: 1px dashed #000 !important; border-radius: 0 !important;
      background: #fff !important; color: #000 !important; box-shadow: none !important;
      page-break-inside: avoid; break-inside: avoid;
      min-height: 4cm; padding: 0.45cm; margin: 0;
    }}
    .topic {{ color: #000 !important; border-bottom: 1px solid #000;
              padding-bottom: 0.15cm; margin-bottom: 0.2cm; }}
    .front, .back {{ color: #000 !important; }}
  }}
</style>
</head>
<body>
  <h1>Study Path Flashcards</h1>
  <p>Total: {len(flashcards)} flashcards · {len(state.get('topics', []))} topics</p>
  {source_note_html}
  {guide_html}
  <div class="cards">{cards_html}</div>
  {warning_html}
</body>
</html>"""

    source_readable = (
        "extracted from the provided syllabus"
        if topics_source == "syllabus_provided"
        else "suggested by the agent (no syllabus provided)"
    )
    summary = (
        f"Study path generated with {len(state.get('topics', []))} topics "
        f"({source_readable}), {len(flashcards)} personalized "
        f"flashcards, and {len(state.get('calendar_events', []))} spaced "
        f"repetition review events in the calendar (.ics)."
    )
    if removed_flashcards:
        summary += (
            f" {len(removed_flashcards)} flashcard(s) were withheld after "
            "verification could not fix a flagged problem."
        )

    return {
        "flashcards_html": html,
        "final_summary": summary,
        "flashcards": flashcards,
        "removed_flashcards": removed_flashcards,
    }
