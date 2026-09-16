"""
Agent state: personalized study path generator.

Pipeline: parse_profile -> extract_topics -> build_schedule ->
generate_flashcards -> validate -> respond

Student input: free-text answers to a context questionnaire + the
syllabus text (pasted by the student, not fetched by the agent -- avoids
depending on internet/scraping during execution).
"""

from typing import TypedDict, List, Dict, Optional


class StudentProfile(TypedDict):
    works: str                # e.g. "yes, as a salesperson" or "does not work"
    interests: List[str]       # e.g. ["soccer", "country music", "cooking"]
    region: str                  # e.g. "rural Ceará", "riverside community near Manaus"
    study_pace: str                # "light" | "moderate" | "intensive" -- how much daily
                                     # study time the student realistically has. Part of
                                     # the student's real context (Freire), not just their
                                     # interests -- affects schedule spacing and flashcard
                                     # load, not just example flavor.
    free_context: str              # anything extra the student mentioned


class ReviewEvent(TypedDict):
    topic: str
    date: str            # YYYY-MM-DD
    review_type: str       # "first_exposure" | "review_1" | "review_2" | "review_3" | "review_4"


class Flashcard(TypedDict):
    topic: str
    type: str            # "CONCEPT" | "USE_CASE" | "PITFALL" | "QA" | "SUMMARY"
    front: str          # question or concept
    back: str              # answer, contextualized with the student's interest when possible
    difficulty: str
    used_interest: str  # the student interest this card used as an example/analogy (from the
                          # profile's `interests`); "" when the card used a generic example or
                          # none -- expected and fine for many cards. Surfaced in the UI as a
                          # small "personalized using: ..." tag so the student sees why the
                          # profile was collected.


# Emoji shown for each Flashcard["type"] in rendered output -- used by
# both respond_node's HTML page and the Streamlit deck, so a card type
# maps to an icon in exactly one place.
TYPE_ICONS = {
    "CONCEPT": "💡",
    "USE_CASE": "🎯",
    "PITFALL": "⚠️",
    "QA": "❓",
    "SUMMARY": "📝",
}


class ValidationIssue(TypedDict):
    issue_type: str  # "conceptual_error" | "forced_contextualization" |
                       # "invalid_schedule" | "invalid_card_type"
    description: str
    affected_excerpt: str
    affected_card_front: str  # exact `front` text of the flashcard this issue is about,
                                # copied verbatim by the reviewer; "" when the issue is not
                                # tied to one specific card (e.g. invalid_schedule). Lets
                                # respond_node drop only the offending card when the retry
                                # loop could not fix it, instead of shipping it with a warning.
    affected_topic: str  # topic the issue belongs to. Always available (the topic is shown
                           # in brackets on every reviewed card), so when the reviewer cannot
                           # pin a content issue to one `affected_card_front`, respond_node
                           # can still withhold that whole topic rather than let an unverified
                           # card through -- veracity over completeness.


class AgentState(TypedDict, total=False):
    # --- Input ---
    questionnaire_answers: str    # free-text answers from the student
    syllabus_text: Optional[str]    # syllabus text pasted by the student, IF they have one
    free_form_goal: Optional[str]    # e.g. "I want to learn basic math for a college exam"
                                       # -- used when the student does NOT have a defined
                                       # syllabus/curriculum and doesn't know exactly what to study
    start_date: str                 # YYYY-MM-DD, study start date

    # --- Filled by `parse_profile` ---
    student_profile: StudentProfile

    # --- Filled by `extract_topics` ---
    topics: List[str]
    topics_source: str  # "syllabus_provided" | "general_suggestion" -- transparency about
                          # whether topics came from the student's real curriculum or from
                          # a model suggestion when they had no syllabus

    # --- Filled by `build_schedule` ---
    calendar_events: List[ReviewEvent]
    ics_content: str  # .ics file ready to import into any calendar app

    # --- Filled by `generate_flashcards` ---
    flashcards: List[Flashcard]
    topic_explanations: Dict[str, str]  # topic -> a short 3-5 sentence plain-language overview
                                          # of the topic, shown to the student BEFORE the
                                          # flashcards as a fixed "study guide" intro (distinct
                                          # from a CONCEPT card, which is just one card among many)

    # --- Filled by `validate`, read by the retry loop ---
    issues_found: List[ValidationIssue]
    approved: bool
    retry_count: int  # how many times generate_flashcards has been retried after a
                        # failed validation -- capped by MAX_FLASHCARD_RETRIES in
                        # nodes.py, so the graph can never loop forever

    # --- Filled by `respond` ---
    flashcards_html: str    # self-contained HTML page with the flashcards, for offline use
    final_summary: str         # summary of the generated study path
    removed_flashcards: List[Flashcard]  # cards pulled from the final set because verification
                                           # flagged a content problem the retry loop could not
                                           # fix -- kept for technical review, never shown to the
                                           # student as reliable material
