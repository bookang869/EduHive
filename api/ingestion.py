from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from core.ingestion import MAX_PAGES, estimate_hours, run_analyze, run_pdf_ingestion

router = APIRouter()


@router.post("/ingest/pdf")
async def ingest_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    study_set_id: str | None = Form(None),
):
    fname = (file.filename or "upload.pdf").lower()
    if not fname.endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are accepted.")

    content = await file.read()

    try:
        from pypdf import PdfReader
        import io
        pages = len(PdfReader(io.BytesIO(content)).pages)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")

    if pages > MAX_PAGES:
        raise HTTPException(status_code=400, detail=f"PDF exceeds {MAX_PAGES}-page limit.")

    from core.db import create_study_set, get_user_id_by_sub
    google_sub = getattr(request.state, "user_sub", None)
    user_id = await get_user_id_by_sub(google_sub) if google_sub else None

    if study_set_id:
        from core.db import get_study_set_owner_sub
        owner_sub = await get_study_set_owner_sub(study_set_id)
        if owner_sub and owner_sub != google_sub:
            raise HTTPException(status_code=403, detail="Forbidden")
    else:
        study_set_id = await create_study_set(user_id)

    background_tasks.add_task(run_pdf_ingestion, study_set_id, file.filename or "upload.pdf", content)
    return {"status": "ingestion started", "study_set_id": study_set_id}


@router.get("/ingest/status")
async def ingest_status(study_set_id: str):
    from core.db import get_ingestion_status
    return {"status": await get_ingestion_status(study_set_id)}



class AnalyzeRequest(BaseModel):
    study_set_id: str


@router.post("/analyze")
async def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_analyze, request.study_set_id)
    return {"status": "analysis started"}


@router.get("/study-materials/{study_set_id}")
async def study_materials(study_set_id: str):
    from core.db import get_study_materials
    return await get_study_materials(study_set_id)


class EstimateRequest(BaseModel):
    study_set_id: str
    deadline: str  # YYYY-MM-DD


@router.post("/estimate")
async def estimate(request: EstimateRequest):
    from core.db import get_topic_scores
    scores = await get_topic_scores(request.study_set_id)
    if not scores:
        raise HTTPException(status_code=404, detail="No topic scores found for this study set.")
    return estimate_hours(scores, request.deadline)


class QuizAttemptRequest(BaseModel):
    quiz_id: str
    score: int
    wrong_topics: list[str] = []


@router.get("/quiz-attempts/{study_set_id}")
async def list_attempts(study_set_id: str):
    from core.db import get_quiz_attempts_for_study_set
    return await get_quiz_attempts_for_study_set(study_set_id)


@router.post("/quiz-attempts")
async def record_attempt(request: Request, body: QuizAttemptRequest):
    from core.db import insert_quiz_attempt, get_user_id_by_sub
    google_sub = getattr(request.state, "user_sub", None)
    user_id = await get_user_id_by_sub(google_sub) if google_sub else None
    await insert_quiz_attempt(body.quiz_id, body.score, body.wrong_topics, user_id)
    return {"status": "recorded"}
