# Attune — Exam & College Entrance Study Path for Students with Unreliable Internet

**A global problem, not a regional one:** an estimated 2.6 billion people — roughly a third of the world's population — remain offline in 2026, according to the International Telecommunication Union. For students, that gap intersects with a hard deadline that makes it especially costly: a national exam or college entrance exam (ENEM/vestibular in Brazil, the GED in the U.S., and equivalents worldwide) doesn't wait for connectivity to improve. This agent is for exactly that student: preparing for a specific exam, without an individual tutor available, and without reliable internet where they actually study. It turns a syllabus (or just a stated goal, like "pass the ENEM in math") into a complete study path: a review schedule grounded in learning science (spaced repetition), exported as a universal calendar file, and flashcards contextualized with the student's real interests. This is not a generic "personalized learning" tool — it is built specifically for exam/college-entrance prep under real connectivity constraints, and grounded in two deliberate pedagogical choices, not just an engineering convenience.

## Grounded in learning science and critical pedagogy

This project rests on two pedagogical foundations, each addressing a different failure mode of typical exam prep — and each is a first-class design decision in the agent, not an afterthought.

**1. Spaced repetition (the forgetting curve).** Hermann Ebbinghaus's forgetting curve research shows that recall drops sharply within days of first exposure to new material, and that reviewing content at *growing* intervals — rather than once, or all at once right before the exam — is what moves it into durable, long-term memory. That's the science behind `build_schedule_node`: instead of a single "study everything" block, the agent schedules first exposure and four follow-up reviews (day 1, 3, 7, 14) per topic, exported as real calendar events the student gets reminded about — not a to-do list they have to remember to check.

**2. Paulo Freire's pedagogy of the oppressed — teaching from the student's own reality.** Freire's central critique of the "banking model" of education (where the teacher deposits abstract, decontextualized knowledge into a passive student) is that it produces knowledge the student can recite but not truly own — because it was never connected to the world the student actually lives in. Freire argued instead for teaching that starts from the learner's lived context: their work, their culture, their concrete daily reality. This is the direct inspiration for `generate_flashcards_node`: the questionnaire captures what the student actually does and cares about (their work, their interests, their region), and that context is used to make abstract concepts concrete — a fraction explained through splitting a soccer match into halves, for a student who plays soccer, means something a decontextualized "1/2 of a pizza" example may not, for a student whose daily reality doesn't look like a stock-photo classroom. This is also **sellable as the differentiator**, not just a pedagogical nicety: it is the reason this agent's flashcards can't be replaced by a generic flashcard deck downloaded from the internet — the personalization is the product, not decoration on top of it.

**Context isn't only about interests — it's also about time, and the agent treats it that way.** A working student and a full-time student don't have the same daily study capacity, and a plan that ignores that isn't really personalized, no matter how good the flashcard examples are. `parse_profile_node` classifies the student's realistic daily study time (`study_pace`: light / moderate / intensive) directly from the questionnaire, and that classification changes two concrete things downstream: `build_schedule_node` spaces topics further apart for a "light" pace (`TOPIC_SPACING_DAYS`), so review sessions don't stack up faster than the student can keep up with, and `generate_flashcards_node` generates fewer, more essential cards per topic (`CARDS_PER_TOPIC`) instead of the same fixed load regardless of how much time the student actually has.

**The two are deliberately kept in tension by design, not left unchecked.** Freire's contextualization is powerful but risky — a forced, unnatural analogy actively hurts comprehension instead of helping it. That risk is exactly why `validate_node` exists as a first-class pipeline step, not an optional extra: it explicitly reviews every flashcard for forced contextualization before the student ever sees it. See the Hot Take section below for what this catches in practice.

## The user and the bottleneck

**Who has this problem, concretely, in two illustrative regions (among many worldwide):**

- **Brazil:** 88% of rural households have internet access, vs. 95.8% in urban areas (IBGE, 2025) — a gap that has narrowed sharply since 2016 (35% vs. 76.5% then), but what remains is increasingly a real infrastructure absence, not a choice: among rural households without internet, 8.9% cite lack of service availability in their area, versus just 0.4% in urban households. Rural internet users also rely far more heavily on mobile-only access with limited data plans (CGI.br, TIC Domicílios 2025) — meaning even "connected" rural households often can't reliably download or stream heavy study content. This shows up concretely for students in rural or underserved regions — from the interior of Bahia to the Amazon region, the sertão of Ceará, or small towns in Minas Gerais and beyond — preparing for the ENEM or a vestibular, often with internet only sporadically (in town, at a relative's house, or at school) but not where they actually study, at home.
- **United States:** an estimated 24 million Americans still lack fixed broadband at the FCC's 100/20 Mbps benchmark, concentrated in rural counties, Tribal lands, and low-income urban areas — combined fixed+5G coverage reaches 98% in U.S. cities but only 61% in rural areas, and a quarter of U.S. school districts still haven't hit the FCC's minimum school bandwidth benchmark. A student in rural Appalachia preparing for the GED faces the structurally same gap.

These two regions are illustrative, grounded examples (Brazil is the context the author knows firsthand, hence the depth of detail) — the underlying problem, and the offline-first design that solves it, generalize to any of the 2.6 billion people affected by the global connectivity gap.

**Why this matters beyond any single student:** education is one of the United Nations' Sustainable Development Goals (SDG 4) precisely because it is considered a foundational, cross-cutting pillar — the UN describes it as a "critical enabler" with transformative effects across the other Sustainable Development Goals, not a self-contained goal on its own. Quality education is directly tied to breaking cycles of poverty and enabling upward socioeconomic mobility. An exam or college entrance exam is often the concrete gate a student has to pass through to access that mobility — so a connectivity gap that specifically degrades exam prep isn't just a study-habits inconvenience, it's a structural barrier sitting on top of the same pillar SDG 4 is meant to secure. This project doesn't solve the broader infrastructure gap (that's a policy and investment problem, not a software one) — it solves the narrower, tractable slice of it: making sure the exam-prep process itself doesn't additionally penalize a student for the connectivity gap they didn't choose to have.

**Connectivity is the central bottleneck of this project, not a side detail.** Most modern exam-prep material assumes available internet: video lessons, interactive apps, online flashcard platforms, cram-school subscriptions. A student without stable internet is left out of that entire ecosystem, even with occasional access — and exam/college-entrance prep specifically has a hard deadline (the exam date), which makes an inefficient, unreviewed study process especially costly.

**Second bottleneck: the silent risk of self-directed study and unguided repetition.** Studying in isolation without a human tutor introduces a dangerous bottleneck: students easily fall into an *illusion of competence* by memorizing abstract formulas or flawed analogies without realizing their conceptual gaps until exam day. Furthermore, manually building a mathematically sound spaced repetition schedule against a fixed exam date is tedious and complex, leading most students to default to inefficient cramming.

**And what if the student doesn't even know what to study for the exam?** Not every student preparing for a college entrance exam or a specific test has a defined syllabus — sometimes they only know "I need to pass the ENEM in math" or "I have a certification exam coming up" in vague terms. The agent covers both cases: if the student has a syllabus, it extracts the real topics from it; if not, the agent **suggests** a reasonable topic breakdown from the stated exam/goal — clearly flagging, visibly in the generated material, that those topics are a suggestion (not an official curriculum), and applying an extra layer of rigor in verification for that case.

## How the agent helps

The agent's two capabilities the challenge asks for specifically — **context** and **verification** — are described first; everything the pipeline grew around them (a self-correction retry loop, real fan-out/fan-in parallelism, a veracity filter that withholds unfixable cards) is documented in the Architecture and Changelog sections below.

1. **Context (student profile):** a simple questionnaire (work, interests, region) generates a profile that is carried through the whole pipeline and used to contextualize the flashcards — without forcing analogies that hurt clarity. **That personalization is made visible, not just claimed:** any flashcard whose example is built on one of the student's stated interests carries a small `🎯 personalized using: <interest>` tag (`used_interest`, kept only when it really matches an interest in the profile), so the student can see exactly where their own life shaped the material — the direct, checkable form of "the personalization is the product".

2. **Verification & Transparent Human-in-the-Loop Decision:** before delivering anything, the agent reviews the flashcards (conceptual errors, forced contextualization) and runs two deterministic checks that need no API call: that the review schedule has its dates in the correct order (`invalid_schedule`), and that every flashcard's type is one of the five allowed taxonomy values (`invalid_card_type`). The system makes its confidence and uncertainties explicitly visible to the student through a verification badge (`✅ Approved` vs `⚠️ Has issues`). The student acts as the qualified final reviewer of their own learning journey, retaining full autonomy to modify, accept, print, or withhold study paths based on clear diagnostic feedback.

When the self-correction retry loop cannot fix a flagged card, it is **withheld** from the student's set: if the reviewer pinned the problem to one card (`affected_card_front`), only that card is dropped and the topic's other verified cards stay; if it could not, the **whole affected topic** is dropped instead — veracity over completeness, so an unverified card never slips through just because it could not be singled out. A conservative placeholder is added only when a topic would otherwise be left empty. The raw finding remains in `issues_found` for technical review; flagged content is never shown as reliable.

Alongside the flashcards, `generate_flashcards_node` also produces a **study guide**: a short 3-5 sentence plain-language overview per topic (`topic_explanations`), shown before the interactive deck so the student reads an introduction to each topic before practicing the questions. It is distinct from a CONCEPT card, which is just one card among several.

**Why a five-type card taxonomy (`CARD_TYPES`), not just question→answer.** A deck that is only Q→A repeated exercises one depth of understanding — recall. So each card is generated as one of five deliberately different types: **CONCEPT** (explain the idea, personalized to the student's context), **USE_CASE** (a concrete application), **PITFALL** (a common mistake plus how to avoid it), **QA** (direct question and detailed answer), **SUMMARY** (fast key-points recall). The mix forces the material to cover recognition, application, error-spotting and compression — the things an exam actually tests — instead of one narrow slice. The type is also a first-class field the deterministic check (`invalid_card_type`) guards, so a malformed card can't silently ship.

## Technical decision: why an `.ics` file instead of the Google Calendar API

We could integrate directly with the Google Calendar API, but that would require OAuth — which would break reproducibility (another person evaluating the project would need their own Google account and credentials just to test it) and add unnecessary technical risk. Instead, the agent generates an **`.ics`** file — the universal calendar format (RFC 5545) — which imports into **any** app (Google Calendar, Outlook, Apple Calendar) with one click, no API key, no OAuth, and works offline once imported. Same experience for the student, much less technical fragility.

## Architecture

```text
BASELINE (required for a fair comparison):
    A single prompt asking for "schedule + flashcards" at once, no
    student profile, no real spaced repetition, no real calendar file.

AGENT SOLUTION:

    START ─┬─▶ parse_profile ──┐
           └─▶ extract_topics ─┴─▶ build_schedule ─▶ generate_flashcards ─▶ validate ─▶ respond
                                                            ▲                    │
                                                            └────────────────────┘
                                                    issues found → retry (max 3 attempts)

    parse_profile ‖ extract_topics   fan out from START and run CONCURRENTLY: no data
                                     dependency (one reads the questionnaire, the other the
                                     syllabus/goal); disjoint writes, so no reducer needed.
    parse_profile          free-text questionnaire → structured student profile
    extract_topics         syllabus pasted by the student → topic list
                           (or a general suggestion, if no syllabus)
    build_schedule         fan-in: waits for BOTH (needs `topics` + `student_profile.study_pace`);
                           applies spaced repetition intervals, generates .ics
    generate_flashcards    per-topic study-guide overview + flashcards contextualized
                           with the student's interests
    validate               VERIFICATION: conceptual error, forced contextualization,
                           invalid schedule, invalid card type
    validate ⟳ generate_flashcards   conditional edge: if issues are found and the retry
                           budget (MAX_FLASHCARD_RETRIES = 3) isn't exhausted, loop back
                           to regenerate with the specific rejection reason; otherwise
                           proceed to respond
    respond                withholds any card still flagged after the retry loop, then
                           emits the self-contained HTML (study guide + flashcards) + summary
```

## How it was measured & Reproducibility

**Primary metric:** pass rate on verification — schedule with correct dates + flashcards with no conceptual error or forced contextualization.

**Secondary metrics:** number of real calendar events generated (the baseline generates none), average time per task, estimated manual human time, cost per task.

**Deterministic Reproducibility:** 11 synthetic test cases are evaluated in `evaluate.py`. To ensure robust evaluation without relying on private data, the suite explicitly includes a **difficult edge case with no topic numbering** — a syllabus given as one running English sentence (`"The course starts with object-oriented programming concepts, then moves into basic data structures, and finishes with an introduction to relational databases."`), which tests whether `extract_topics_node` can still pull a clean topic list from unstructured prose. Any second reviewer can run `python evaluate.py` to trace every score, issue, and self-correction loop back to its source and reproduce the exact verification outcomes.

| Metric | Baseline | Agent Solution | Change |
|---|---|---|---|
| Pass rate (verification) | N/A (no verification) | 10/11 (90.9%) | Agent introduces verification the baseline doesn't have. Before the self-correction loop (Iteration 4), pass rate was 6/11 (54.5%) — the retry loop raised it to 10/11 by regenerating flashcards with the specific rejection reason when validation fails |
| Real calendar events generated | 0 (loose text, no `.ics`) | 160 | Structural difference — baseline produces no usable artifact |
| Average time per task (s) | 26.64 | 58.70 | Roughly 2x the pre-retry-loop time (28.78s), because cases needing correction now do generation+validation twice — a deliberate trade-off for the pass-rate gain above |
| Estimated manual human time (min) | 45 min (estimate) | ~1.0 min (58.70s) | ~46x faster than doing this manually — still a large margin even after the retry loop's added time cost |
| Flashcards delivered / withheld by verification | N/A (no verification) | instrumented, awaiting a clean run | `evaluate.py` now sums `removed_flashcards` across the 11 cases (see the "Flashcards delivered / withheld" line it prints); the number can't be filled here until a full run completes — see note below |
| Cost per task (USD) | $0 (Gemini free tier) | $0 (Gemini free tier) | No cost difference — both free at this volume |

> **Note on the two baseline times.** The table reports **26.64 s** for the baseline and **58.70 s** for the agent, from the run that produced the 10/11 pass rate. The changelog rows below cite **16.62 s** baseline, from an earlier run — the one *before* the self-correction loop, the same run that produced the 6/11 evidence. Both are real measurements from different moments: baseline time varies noticeably between runs because of Gemini API latency, so this is genuine run-to-run variance, not a typo.
>
> **Note on freshness.** These numbers are from the Iteration 4 run. They *predate* the veracity filter (Iterations 5 / 5.1), the fan-out/fan-in parallelization (Iteration 6), and the raised `CARDS_PER_TOPIC` (`{2,3,4}` → `{3,4,5}`). Three attempts to re-run `evaluate.py` on the current pipeline did not complete: one hit a malformed-JSON response from the model (a trailing comma before `}` — now tolerated by `_parse_json_response`, with regression tests), and two hit a transient local connection drop (`httpx.ReadError [WinError 10053]`) on the first request. The pass-rate story (6/11 → 10/11 via the retry loop) is unaffected — `approved` is still set the same way by `validate_node` — but the time figure should be read as an upper bound: parallelization (Iteration 6) removes the shorter of two LLM calls from the critical path. The withheld-cards metric is instrumented and will be filled on the next clean run.

## Improvement Changelog

| Stage | What you tried and why | Evidence | Decision/Learning |
|---|---|---|---|
| Baseline | Single prompt, no profile, no real spaced repetition | 16.62s avg per task, 0 real calendar events, no verification | Established the starting point |
| Iteration 1 | Structured student profile, carried through the whole pipeline | Profile correctly extracted in all 11 test cases, including a Portuguese-language case | Kept |
| Iteration 2 | Real spaced repetition (.ics), instead of dates suggested in loose text | 160 real calendar events generated across 11 cases vs. 0 for baseline | Kept — structural improvement, not incremental |
| Iteration 3 | Verification added after observing the risk of forced contextualization | 6/11 (54.5%) pass rate — caught real issues in ~45% of cases, including a nonsensical "more musicians = faster album recording" analogy for inverse proportion | Kept — the failure rate confirms the risk was real, not hypothetical |
| Final | Full pipeline: 28.78s avg per task vs. 45min estimated manual effort (~94x faster); difficult case (unstructured syllabus) still approved, generating 15 correct events | evaluate.py full run, 11 cases | Main contribution: verification is the load-bearing capability — without it, ~45% of outputs would ship with an uncaught error |
| Bugfix (live) | Fixed `_parse_json_response` crashing when Gemini 3.6 Flash returns `.content` as a list of blocks instead of a plain string (`AttributeError: 'list' object has no attribute 'strip'`) | 12/12 tests passing after fix, including new regression test `test_extract_topics_handles_list_content_response` reproducing the exact shape that crashed live | Kept — normalizing LLM output shape at a single boundary function is safer than assuming a fixed shape throughout the pipeline; see Hot Take for the full lesson |
| Iteration 4 | Closed the self-correction loop: `validate` now routes back to `generate_flashcards` with the rejection reason when issues are found, capped at 2 total attempts (`retry_count` in `AgentState`) | Pass rate went from 6/11 (54.5%) to **10/11 (90.9%)**; average time roughly doubled (28.78s → 58.70s) as the trade-off | Kept — large reliability gain for a proportionate, expected time cost; 1/11 case still fails after 2 attempts, now a visible limitation instead of a hidden one |
| Doc & consistency pass | Full README/CLAUDE.md review against the code + low-risk cleanup (Hot Take wording, 5/11-not-6/11 fix, baseline-time note, retry edge in both architecture diagrams, `invalid_card_type` / `GET /health` documented, `TYPE_ICONS` unified into `state.py`, tuning constants regrouped, dead Streamlit state removed) | 24/24 tests passing after each change; `streamlit_app.py` verified via `py_compile` (no automated coverage) | Kept — documentation/consistency only, no behaviour change |
| Iteration 5 | Content integrity: (a) a per-topic **study guide** (`topic_explanations`) shown before the deck; (b) after the retry loop gives up, `respond_node` **withholds** the specific cards still flagged for a `conceptual_error` / `forced_contextualization` (keeps the topic's other verified cards; adds one conservative placeholder only if a topic would be emptied). `issues_found` stays for technical review | 32/32 tests passing (8 new). `evaluate.py` deferred to a manual run to save Gemini quota | Kept — veracity over completeness; the third Hot Take example is now a risk the pipeline closes, not just reports |
| Iteration 5.1 | Closed a gap in the withholding rule: an unfixed content issue the reviewer could not pin to a card used to leave that card in place. `ValidationIssue` gains `affected_topic`; when an issue can't be pinned to one card, the **whole affected topic** is withheld instead (last resort with no topic either: every topic that still has cards is emptied). Topics with no issue are untouched | 33/33 tests passing (one test replaced by two; `affected_topic` normalization + front-over-topic precedence asserted). `evaluate.py` not run | Kept — the "leave the ambiguous card in place" behaviour contradicted the veracity-over-completeness goal |
| Iteration 6 | `graph.py` fans `parse_profile` and `extract_topics` out from `START` to run concurrently (no data dependency); `build_schedule` fans back in, waiting for both (it needs `topics` **and** `student_profile.study_pace`). Sequential from there, retry loop unchanged. Integration tests switched from positional `side_effect` lists to a prompt-content dispatcher (the two fan-out calls arrive in any order) | 33/33 passing, stable over 5 consecutive runs. One instrumented real run: the two calls measured overlapping fully; wall 94.0s vs ~96.4s serial — saving is the shorter of the two calls off the critical path (2.4s here; % is noisy, this run hit big Gemini latency outliers) | Kept — real structural parallelism, zero behaviour change |
| Iteration 7 | `CARDS_PER_TOPIC` raised `{2,3,4}` → `{3,4,5}` (the veracity filter can drop cards, so a low budget leaves topics thin); new `Flashcard.used_interest` + `🎯 personalized using: <interest>` deck tag (kept only when it matches a real profile interest); `_parse_json_response` now tolerates a trailing comma before `}` / `]` (one repair-and-retry pass; truncation still raises); `evaluate.py` sums `removed_flashcards` across the 11 cases | 44/44 tests passing (11 new). **Full `evaluate.py` re-run did not complete** across three attempts — one malformed-JSON response (now handled), two transient `httpx.ReadError [WinError 10053]` — so the metrics table keeps the Iteration 4 numbers with a freshness note | Kept — pass-rate mechanism unchanged; table time is now an upper bound; withheld-cards metric instrumented, pending a clean run |
| Engineering discipline (ongoing) | JS inside a Python f-string (the Streamlit deck) is a footgun — twice it shipped broken with no stack trace. Rule: every generated JS block is run through `node --check` before it's done; `tests/test_streamlit_deck.py` lifts `build_flashcard_deck_html` out via `ast` + `exec` (no Streamlit import) to keep the rendered deck under automated test | Two live breakages, then zero since the gate | Kept — cheap gate for a bug class with no runtime error |
| Flashcard type icons | Deck's five type emoji (💡🎯⚠️❓📝) swapped for inline outline SVGs (`TYPE_ICONS_SVG` in `streamlit_app.py`, deck only; `state.py` emoji still feed the offline HTML). `stroke="currentColor"`, 16–18px, no fill, fully embedded | 46/46 tests (2 new); deck `<script>` `node --check` rc 0 | Kept — visual/icon-style swap, no logic change |
| Iteration 8 | `MAX_FLASHCARD_RETRIES` raised 2 → 3 — one more self-correction pass before the graph gives up and `respond_node` withholds the card. One-line config change | 46/46 tests passing (`test_graph_gives_up_after_max_retries_without_infinite_loop` now derives the worst-case call count from the constant: `2 + 2 * MAX_FLASHCARD_RETRIES` = 8; the 2 tests added since Iteration 7 cover the deck's inline-SVG type icons). `evaluate.py` not re-run — config change, no result claim | Kept — an extra shot at fixing a flagged analogy costs ~one more LLM round-trip, only on cases that were already failing |

## Hot Take / Insights

**Failure mode observed during development: LLM output shape isn't stable across model versions, and code that assumes it is will break silently in production, not in tests.** While testing this project live, a call to `parse_profile_node` crashed with `AttributeError: 'list' object has no attribute 'strip'`. The root cause: Gemini 3.6 Flash sometimes returns `response.content` as a list of content blocks (`[{"type": "text", "text": "..."}]`) instead of a plain string — a shape the original `_parse_json_response` helper didn't handle, because it was written and tested against the plain-string shape that was previously typical.

**Unit tests that mock the LLM response can pass 100% while still encoding a wrong assumption about that response's shape** — the mock is only as realistic as the assumption behind it, so a whole green suite can be blind to the exact thing that breaks in production. The tests here (`tests/test_nodes.py`) were all green before this bug surfaced live: they tested the parsing logic correctly, but every mock used the same string-shaped `.content` the code already expected, so the mismatch between "what we assumed the LLM returns" and "what the LLM actually returns" was invisible to the test suite.

**What we'd change building the next agent from scratch, based on this:** normalize and validate the raw shape of any LLM response at a single, well-tested boundary function immediately after the API call — before any downstream code touches it — rather than assuming a fixed shape throughout the pipeline. We did this here (`_parse_json_response` now handles both `str` and `list` shapes, with a regression test — `test_extract_topics_handles_list_content_response` — that reproduces the exact failure), but doing it reactively after a live crash is a worse position than designing for output-shape variance from the start, especially as model providers iterate their APIs over a project's lifetime.

**Second failure mode, and evidence it isn't rare: forced contextualization is a real, frequent risk, not a hypothetical edge case.** Running the full evaluation (`evaluate.py`, 11 cases), `validate_node` flagged issues in 5/11 cases (a 6/11, i.e. 54.5%, pass rate) — meaning verification caught something in nearly half of all generations. One concrete example: for a flashcard about inverse proportion, the model generated the analogy "doubling the number of musicians in a band halves the time needed to record an album" — which is backwards (more musicians recording together doesn't speed up recording the way more painters speed up painting a wall; if anything it's harder to coordinate). The analogy sounded plausible on the surface but was mathematically wrong for the concept it was supposed to teach.

**A third real example, and how the design now handles it.** Two more flagged cards from the same evaluation runs: (1) a "percentage" card that explained the concept through a streaming playlist but used **50 tracks as the whole** — treating, say, 30 of 50 tracks as "30%" — which directly contradicts the definition it was teaching (*per cent* = per hundred); (2) an "audio export takes proportionally longer" card that treated export time as a **strict direct proportion** of clip length, without acknowledging it also depends on plugins and processing, so "twice as long" fails as a hard rule. Both are the same failure shape as the musicians analogy: locally plausible, globally wrong for the concept. As of the change described next, a flagged card like this **no longer reaches the student at all** when the retry loop cannot fix it — `respond_node` drops the specific card the reviewer pinned (`affected_card_front`), keeping the topic's other verified cards; and if the reviewer flagged a real problem but could not pin the exact card, it drops that **whole topic** rather than gamble on which card was meant (a single conservative placeholder replaces an emptied topic). The raw finding stays only in `issues_found` for technical review. The 5/11 "issue observed" rate stays valid as a measurement, but the risk it represents is now closed by design, not merely documented.

This validates a design choice made early and speculatively (adding `validate_node` specifically to catch forced contextualization) with real usage data, not just intuition: **the ~45% failure rate is exactly the kind of number that justifies verification being a first-class pipeline step rather than an optional add-on.** Without it, an incorrect analogy would have shipped to the student with the same visual confidence as a correct one — arguably worse than no analogy at all, since it actively teaches the wrong intuition about the underlying math. Originally the pipeline only flagged this to the student (visible ⚠️ warning); **Iteration 4 closed that loop** — `validate` now routes back to `generate_flashcards` with the specific rejection reason when it finds a problem, capped at 3 total attempts (`MAX_FLASHCARD_RETRIES`, raised from 2 in Iteration 8), so most flagged cases are corrected automatically before the student ever sees them (pass rate rose from 6/11 to 10/11 on the same cases). When the retry still cannot fix a card, that card is now **withheld from the student's set entirely** rather than shown with a warning — a residual ⚠️ means content was removed, never that unverified content was left in.

**A separate engineering insight, from a self-inflicted bug: generating JavaScript inside Python f-strings is a footgun, so we put a mechanical gate on it.** The Streamlit flashcard deck is one big HTML/CSS/JS string built by `build_flashcard_deck_html`. Twice it shipped broken because an f-string ate a JS escape: a `\n` inside a `//` comment became a real newline that split the comment and left a stray backtick opening an unterminated template literal, blanking the whole deck with no error. The fix isn't "be more careful" — it's a rule: **every JavaScript block generated inside an f-string is extracted and run through `node --check` before it's considered done**, and `tests/test_streamlit_deck.py` lifts `build_flashcard_deck_html` out with `ast` + `exec` (without importing the Streamlit module) so the rendered deck output is under automated test. Cheap gate, catches the exact class of bug that has no stack trace.

## How to run (from scratch)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# fill in GOOGLE_API_KEY in .env (get one free at https://aistudio.google.com/apikey)
```

**Run the API:**

```bash
uvicorn app.main:app --reload
```

Open `localhost:8000/docs`. Endpoints:

- `GET /health` — liveness check (returns `{"status": "ok"}`)
- `POST /generate-path` — full agent solution (JSON with profile, topics, flashcards HTML, and .ics content)
- `POST /generate-path-baseline` — simple baseline
- `POST /download-calendar` — downloads the `.ics` file directly
- `POST /download-flashcards` — downloads the flashcards HTML page directly

**Run the visual interface (Streamlit):**

```bash
# in a SECOND terminal, with the API from the step above already running
streamlit run streamlit_app.py
```

Opens automatically in your browser, with two tabs:

- **📚 Generate** — fill in the form (profile + syllabus or goal), click "Generate my study path", and browse the result: metrics, an interactive flashcard viewer (⬅️ Previous / 🔄 Flip / Next ➡️, front/back color-coded) with per-card self-assessment (👍 I knew it / 👎 I didn't) and a running session score, plus a horizontally scrollable mini-board of numbered tiles to jump straight to any card, and three download buttons.
- **📜 Saved History** — every generated path is saved locally to `history.json`, so it survives a page reload (F5). Reopen any past result directly, without calling the API again.

Each flashcard is tagged with one of five types (💡 CONCEPT, 🎯 USE_CASE, ⚠️ PITFALL, ❓ QA, 📝 SUMMARY) — see `CARD_TYPES` in `app/graph/nodes.py` — so review isn't just repeated question→answer, it mixes explanation, practical application, common-mistake warnings, and fast-recall summaries.

**The three download buttons** give the same content in three offline-friendly forms: `study_path.ics` (calendar), `flashcards.html` (self-contained page), and `flashcards_anki.csv` (front/back CSV that Anki imports directly via *File → Import*, no header row).

**Test the offline mode for real:** download the `.ics` and import it into your calendar app (works without internet afterward). Download `flashcards.html`, disconnect from the internet, open the file directly in a browser (`file:///...`). The offline HTML also carries a print stylesheet (`@media print`): it lays the cards out as a two-column grid with dashed trim lines and no background fills, so you can print and cut physical flashcards.

**Run the full evaluation (baseline vs agent, same cases):**

```bash
python evaluate.py
```

**Run the tests:**

```bash
pytest tests/ -v
```

**Versions and cost:** Python 3.10+, `gemini-3.5-flash-lite` model (free tier — chosen over `gemini-3.6-flash` specifically for its more generous free-tier daily request quota, since `evaluate.py` alone makes dozens of calls per run). A full `evaluate.py` run (11 cases × baseline + agent, with the retry loop) is roughly **15–25 minutes**, dominated almost entirely by Gemini API latency, which varies a lot run to run (individual calls have been observed anywhere from ~3 s to ~50 s).

## Example input

**With syllabus (main path):**

```json
{
  "questionnaire_answers": "I work as a shop salesperson, I like soccer and barbecue, I live in Bahia.",
  "syllabus_text": "1. Fractions\n2. Percentages\n3. Rule of three",
  "start_date": "2026-09-01"
}
```

**Without syllabus, only a goal (student who doesn't know exactly what to study):**

```json
{
  "questionnaire_answers": "I work as a shop salesperson, I like soccer and barbecue, I live in Bahia.",
  "free_form_goal": "I want to learn basic math for a college entrance exam",
  "start_date": "2026-09-01"
}
```

In this case, the response includes `"topics_source": "general_suggestion"`, and the generated material (HTML) shows a note warning that the topics were suggested, not extracted from a real curriculum.

**Works in Portuguese too, from different regions of Brazil (real target users):** since the questionnaire is interpreted by the LLM, not by fixed parsing, students can answer in their own language — the code stays in English, but the agent understands the input regardless.

```json
{
  "questionnaire_answers": "Trabalho numa fazenda de café no interior de Minas Gerais, gosto de churrasco e de ler livros.",
  "syllabus_text": "1. Sistema solar\n2. Movimento de rotação e translação",
  "start_date": "2026-09-01"
}
```

The same design applies directly to rural/underserved U.S. students (Appalachia, Tribal lands, or any of the ~24 million Americans without reliable fixed broadband):

```json
{
  "questionnaire_answers": "I work part-time at a farm supply store, I like hunting and country music, I live in rural Appalachia with spotty cell signal and no home broadband.",
  "free_form_goal": "I want to pass the GED math section",
  "start_date": "2026-09-01"
}
```

## Ethical use and compliance with the challenge's ground rules

**What existed before vs. what was built (rule 02):** this project was built entirely during the competition. The only things "already known" beforehand are the stack (Python, FastAPI, LangGraph, LangChain) and general software engineering knowledge — no pre-existing code, template, or repository was reused. The idea evolved from a simpler version (offline material generator by topic/grade) to this version with student profile, spaced repetition, and contextualized flashcards, documented in `CHANGELOG.md`.

**Licenses and terms of service (rule 03):** uses the Gemini API within the free tier (Google AI Studio), and standard open-source libraries (FastAPI, LangGraph, LangChain — MIT/Apache 2.0 licenses). No usage outside these tools' terms of service.

**Consequential actions and human approval (rule 04):** the agent takes no autonomous action in the real world — it only generates files (`.ics`, `.html`) that the user decides to import/open manually. Every final action (importing the calendar, using the flashcards) is the user's explicit choice.

**Qualified human reviewer & Human-in-the-Loop (rule 05):** the target user of this project is precisely someone preparing in isolation who does not have a human tutor available for individual review. Therefore, the system embeds human-in-the-loop principles directly into the design: `validate_node` provides an automated verification layer, and the application explicitly displays verification metrics and a badge (`✅ Approved` vs `⚠️ Has issues`). The student acts as the qualified final reviewer of their personalized study material, retaining full autonomy to review diagnostic warnings, edit topics, or accept the generated files. For advanced topics, the system transparently recommends cross-checking with official course materials.

**Data used (rule 07):** all student profiles used in testing (`evaluate.py`, `tests/`) are synthetic. No real student data is used at any point.

**Credentials (rule 08):** `GOOGLE_API_KEY` stays only in the local `.env`, which is in `.gitignore` — never included in the submission.
