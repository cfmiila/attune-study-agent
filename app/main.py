"""
Personalized study path agent API.
"""

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, model_validator

from app.graph.graph import agent
from app.graph.nodes import generate_baseline_path

load_dotenv()

app = FastAPI(
    title="Personalized Study Path",
    description=(
        "Agent that generates a spaced repetition study path (.ics "
        "calendar file) and flashcards contextualized with the "
        "student's interests, with pedagogical verification. Works "
        "both with a real syllabus and with a free-form goal, for "
        "students who don't know exactly what to study."
    ),
    version="0.2.0",
)


class GeneratePathRequest(BaseModel):
    questionnaire_answers: str
    syllabus_text: str | None = None
    free_form_goal: str | None = None
    start_date: str  # YYYY-MM-DD format

    @model_validator(mode="after")
    def check_syllabus_or_goal(self):
        if not (self.syllabus_text or self.free_form_goal):
            raise ValueError(
                "Provide at least one of: syllabus_text (if you have a "
                "defined curriculum) or free_form_goal (if you only know "
                "what you want to learn, with no specific syllabus)."
            )
        return self


def _invoke_agent(request: GeneratePathRequest) -> dict:
    return agent.invoke(
        {
            "questionnaire_answers": request.questionnaire_answers,
            "syllabus_text": request.syllabus_text,
            "free_form_goal": request.free_form_goal,
            "start_date": request.start_date,
        }
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate-path")
async def generate_path(request: GeneratePathRequest):
    """Generates the full study path using the agent pipeline (with verification)."""
    result = _invoke_agent(request)
    return {
        "student_profile": result["student_profile"],
        "topics": result["topics"],
        "topics_source": result["topics_source"],
        "final_summary": result["final_summary"],
        "approved": result["approved"],
        "issues_found": result.get("issues_found", []),
        "flashcards_html": result["flashcards_html"],
        "ics_content": result["ics_content"],
        "num_flashcards": len(result.get("flashcards", [])),
        "retry_count": result.get("retry_count", 0),
        "flashcards": result.get("flashcards", []),
        "topic_explanations": result.get("topic_explanations", {}),
        "removed_flashcards": result.get("removed_flashcards", []),
        "num_calendar_events": len(result.get("calendar_events", [])),
    }


@app.post("/generate-path-baseline")
async def generate_path_baseline_endpoint(request: GeneratePathRequest):
    """Baseline: a direct prompt, no profile, no real spaced repetition."""
    if not request.syllabus_text:
        raise HTTPException(
            status_code=400,
            detail="The comparison baseline requires syllabus_text (the "
            "baseline does not have the topic-suggestion path the agent has).",
        )
    text = generate_baseline_path(request.syllabus_text)
    return {"raw_result": text}


@app.post("/download-calendar")
async def download_calendar(request: GeneratePathRequest):
    """Returns the .ics file, ready to import into any calendar app."""
    result = _invoke_agent(request)
    return Response(
        content=result["ics_content"],
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="study_path.ics"'},
    )


@app.post("/download-flashcards")
async def download_flashcards(request: GeneratePathRequest):
    """Returns the flashcards HTML page, ready for offline use."""
    result = _invoke_agent(request)
    return Response(
        content=result["flashcards_html"],
        media_type="text/html",
        headers={"Content-Disposition": 'attachment; filename="flashcards.html"'},
    )
