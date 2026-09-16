"""
Compares the baseline with the agent solution on the same cases, using
the format required by the challenge.

Primary metric: pass rate on verification (valid schedule + no
conceptual error/forced contextualization in the flashcards) -- directly
captures what matters to the student: is the material reliable and does
the path make sense?

Secondary metrics: time per task, estimated human time saved, cost per
task, number of real calendar events generated (the baseline doesn't
generate a real calendar file, so this metric alone already shows a
structural difference).
"""

import time
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()

from app.graph.graph import agent
from app.graph.nodes import generate_baseline_path

TEST_CASES = [
    {
        "questionnaire_answers": "I work as a shop salesperson, I like soccer and barbecue, I live in rural Bahia.",
        "syllabus_text": "1. Fractions\n2. Percentages\n3. Rule of three",
        "start_date": "2026-09-01",
    },
    {
        "questionnaire_answers": "I don't work, I study full time, I like country music and cooking.",
        "syllabus_text": "1. French Revolution\n2. Enlightenment\n3. American Independence",
        "start_date": "2026-09-01",
    },
    {
        "questionnaire_answers": "I work part-time as a hairdresser, I like TV shows and makeup.",
        "syllabus_text": "1. Solar system\n2. Rotation and translation movement",
        "start_date": "2026-09-01",
    },
    {
        "questionnaire_answers": "I work as a rideshare driver, I like cars and technology.",
        "syllabus_text": "1. Object-oriented programming\n2. Data structures\n3. Relational databases",
        "start_date": "2026-09-01",
    },
    {
        "questionnaire_answers": "I work as a nursing technician, I like medical shows and healthy cooking.",
        "syllabus_text": "1. Circulatory system anatomy\n2. Cardiac physiology\n3. First aid",
        "start_date": "2026-09-01",
    },
    {
        "questionnaire_answers": "I don't work, I play video games in my free time, I live in Salvador.",
        "syllabus_text": "1. Programming logic\n2. Sorting algorithms\n3. Time complexity",
        "start_date": "2026-09-01",
    },
    {
        "questionnaire_answers": "I work as a bricklayer, I like soccer and weekend barbecue.",
        "syllabus_text": "1. Plane geometry\n2. Areas and perimeters\n3. Pythagorean theorem",
        "start_date": "2026-09-01",
    },
    {
        "questionnaire_answers": "I work as a dance teacher, I like music and traveling.",
        "syllabus_text": "1. Rhythm and musical meter\n2. History of Brazilian music\n3. Percussion instruments",
        "start_date": "2026-09-01",
    },
    {
        "questionnaire_answers": "I work as a store cashier, I like soap operas and crafting.",
        "syllabus_text": "1. Present tense verbs\n2. Subject-verb agreement\n3. Basic punctuation",
        "start_date": "2026-09-01",
    },
    {
        "questionnaire_answers": "I work as a motorcycle mechanic, I like motocross and barbecue.",
        "syllabus_text": "1. Newton's laws\n2. Kinetic and potential energy\n3. Friction and forces",
        "start_date": "2026-09-01",
    },
    # Difficult case: syllabus with no clear numbering, topics mixed in
    # running text -- tests the robustness of topic extraction against a
    # less structured input format than the other cases.
    {
        "questionnaire_answers": "I work as a rideshare driver, I like cars and technology.",
        "syllabus_text": (
            "The course starts with object-oriented programming concepts, "
            "then moves into basic data structures, and finishes with an "
            "introduction to relational databases."
        ),
        "start_date": "2026-09-01",
    },
]

# Conservative estimate of human time to do manually what the agent does
# in one run: research spaced repetition, build a coherent schedule,
# create ~15 flashcards contextualized with the student's interests.
# Comparison point for the "Human time per task" row suggested by the
# challenge.
HUMAN_MANUAL_TIME_MINUTES = 45

# Gemini 2.5 Flash is on the free tier (aistudio.google.com) for the
# volume used in this project -- real execution cost is $0. Reported
# explicitly to fill the "Cost per task" row suggested by the challenge,
# instead of simply omitting it.
COST_PER_TASK_USD = 0.0


@dataclass
class CaseResult:
    time_s: float
    approved: bool | None
    num_calendar_events: int = 0
    num_flashcards: int = 0
    num_removed: int = 0
    issues: List[dict] = field(default_factory=list)


def evaluate_agent(case: dict) -> CaseResult:
    start = time.time()
    result = agent.invoke(case)
    elapsed = time.time() - start
    return CaseResult(
        time_s=elapsed,
        approved=result.get("approved"),
        num_calendar_events=len(result.get("calendar_events", [])),
        num_flashcards=len(result.get("flashcards", [])),
        num_removed=len(result.get("removed_flashcards", [])),
        issues=result.get("issues_found", []),
    )


def evaluate_baseline(case: dict) -> CaseResult:
    start = time.time()
    generate_baseline_path(case["syllabus_text"])
    elapsed = time.time() - start
    # The baseline does not generate real calendar events and doesn't go
    # through verification -- by design, to show the structural
    # difference.
    return CaseResult(time_s=elapsed, approved=None)


def main():
    print("--- Evaluating BASELINE (single prompt) ---")
    baseline_results = [evaluate_baseline(c) for c in TEST_CASES]

    print("--- Evaluating AGENT (profile + spaced repetition + verification) ---")
    agent_results = [evaluate_agent(c) for c in TEST_CASES]

    approved = sum(1 for r in agent_results if r.approved)
    baseline_avg_time = sum(r.time_s for r in baseline_results) / len(baseline_results)
    agent_avg_time = sum(r.time_s for r in agent_results) / len(agent_results)
    total_events = sum(r.num_calendar_events for r in agent_results)
    total_flashcards = sum(r.num_flashcards for r in agent_results)
    total_removed = sum(r.num_removed for r in agent_results)
    cases_with_removal = sum(1 for r in agent_results if r.num_removed)

    print("\n=== RESULT ===")
    print(f"{'Metric':<40}{'Baseline':<25}{'Agent':<20}")
    print(
        f"{'Pass rate (verification)':<40}"
        f"{'N/A (no verification)':<25}"
        f"{f'{approved}/{len(agent_results)}':<20}"
    )
    print(
        f"{'Real calendar events generated':<40}"
        f"{'0 (loose text, no .ics)':<25}"
        f"{total_events:<20}"
    )
    print(
        f"{'Flashcards delivered / withheld':<40}"
        f"{'N/A (no verification)':<25}"
        f"{f'{total_flashcards} / {total_removed} withheld ({cases_with_removal}/{len(agent_results)} cases)':<20}"
    )
    print(
        f"{'Average time per task (s)':<40}"
        f"{baseline_avg_time:<25.2f}"
        f"{agent_avg_time:<20.2f}"
    )
    print(
        f"{'Estimated manual human time (min)':<40}"
        f"{HUMAN_MANUAL_TIME_MINUTES:<25}"
        f"{f'~{agent_avg_time/60:.1f} min (agent)':<20}"
    )
    print(
        f"{'Cost per task (USD)':<40}"
        f"{COST_PER_TASK_USD:<25}"
        f"{COST_PER_TASK_USD:<20}"
        "(both on Gemini's free tier)"
    )

    print("\n--- Difficult case (syllabus with no clear numbering) ---")
    difficult_case = agent_results[-1]
    print(
        f"Approved: {difficult_case.approved}, extracted topics generated "
        f"{difficult_case.num_calendar_events} events"
    )
    if difficult_case.issues:
        print(f"Issues: {difficult_case.issues}")


if __name__ == "__main__":
    main()
