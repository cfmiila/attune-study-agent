# Project context

**micro1 Agentic Workflows Hackathon** (Aug 28-30, 2026).

The Streamlit app ships under the name **Attune** (`page_title` /
header in `streamlit_app.py`); the README title carries both the name
and the descriptive subtitle.

## The problem

Students preparing for a specific exam or college entrance exam (ENEM,
vestibular, technical certifications) who study on their own — without
an individual tutor available, **and without reliable internet access**
(rural/underserved areas, unstable connection, or only sporadic
access) — don't have a review schedule grounded in learning science
(spaced repetition), and generic exam-prep material doesn't connect
with their reality (contrary to Paulo
Freire's idea of teaching from the student's own context).

## Architecture

```
BASELINE: a single prompt, no student profile, no real spaced
          repetition, no real calendar file.

AGENT:    START -+-> parse_profile --+
                +-> extract_topics --+-> build_schedule
          -> generate_flashcards -> validate -> respond
                                        ^            |
                                        +------------+
                             issues found -> retry (max 3 attempts)

  parse_profile || extract_topics:  fan out from START, run CONCURRENTLY.
                        No data dependency (one reads questionnaire_answers,
                        the other syllabus_text/free_form_goal); each writes
                        disjoint keys, so no reducer is needed on AgentState.
  parse_profile:      free-text questionnaire -> structured student profile
  extract_topics:      syllabus pasted by the student -> topic list
                        (OR a general suggestion, if the student has no
                        syllabus, only a free-form goal)
  build_schedule:       fan-in: waits for BOTH (needs `topics` and
                        `student_profile.study_pace`). Applies spaced
                        repetition intervals (Ebbinghaus), generates an
                        .ics file (universal calendar, no OAuth). From here
                        the pipeline is sequential; the retry loop is unchanged.
  generate_flashcards:  per-topic study-guide overview (topic_explanations)
                        + flashcards contextualized with the student's interests
  validate:              VERIFICATION -- conceptual error, forced
                        contextualization, out-of-order schedule,
                        invalid card type. Each content issue names the
                        offending card via affected_card_front and its
                        topic via affected_topic.
  validate -> generate_flashcards:  conditional edge (add_conditional_edges).
                        If validate finds issues and retry_count <
                        MAX_FLASHCARD_RETRIES (3), loop back to regenerate
                        flashcards with the specific rejection reason;
                        otherwise go to respond.
  respond:                after the retry loop, withholds flagged content --
                        the pinned card if affected_card_front matches one,
                        otherwise the whole affected_topic (last resort with
                        no topic: every topic that still has cards). Topics
                        with no issue are untouched; conservative placeholder
                        only if a topic would be emptied. Then builds the
                        self-contained HTML (study guide + flashcards) + summary
```

## Important technical decision: why .ics instead of the Google Calendar API

Real integration with the Google Calendar API requires OAuth -- this
would break Reproducibility (another person would need their own
account+credentials just to test) and adds unnecessary time risk. The
.ics file is the universal calendar format (RFC 5545): imports into
Google Calendar, Outlook, Apple Calendar, with no API key, no OAuth, and
works offline once imported. Delivers the same end-user experience with
much less technical fragility.

## Judging criteria (score out of 100)
| Criterion | Points |
|---|---|
| Agent Solution & Engineering | 30 |
| End to End Quality | 20 |
| Problem & User Value | 15 |
| Measured Improvement | 15 |
| Reproducibility | 15 |
| Hot Take / Insights | 5 |

## This challenge's rules
- Compare against a fair baseline, same cases (see `evaluate.py`)
- CHANGELOG in the format: Stage | What tried and why | Evidence | Decision/Learning
- Only synthetic/public data -- student profiles in tests are fictional
- Every result claim points to evidence

## Palette (Streamlit UI — the real current values, from `streamlit_app.py`)

Analogous blue-violet family plus two deliberately off-family semantic
colours for status. Keep it; only refine how it is applied.

- Page background: `#F5F3FE` (very light lilac); muted body text `#4A4F6A`
- Hero band + primary buttons + section headings: `#0B2E7C` (navy);
  button hover `#14409E`; text on the hero `#FCFCFD` / sub `#C7CBE0`
- Purple accent (focus rings, back-of-card labels, the `🎯 personalized
  using` tag): `#3D2B7C`
- Lilac surfaces (badges, mini-board tiles, card back gradient):
  `#DEE0FB` and `#EDEBFE`; light-blue callout box `#D9EBFE`
- Status green (`✅ Approved` badge, "knew it"): `#16A34A`
- Status amber (`⚠️ Has issues` badge, "didn't"): `#F59E0B`

## Code rules
- `validate_node` has both a deterministic check (schedule) and an
  LLM-based one (conceptual/contextualization) -- don't remove the
  deterministic one, it doesn't depend on an API call and is more
  reliable for that specific check
- Flashcard contextualization must NEVER force an analogy that hurts
  clarity -- this is explicit in the `generate_flashcards_node` prompt
- Every relevant change gets an entry in CHANGELOG.md
