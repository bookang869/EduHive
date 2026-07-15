"""Background ingestion tasks: PDF, web search, weak-topic analysis, study plan."""
from __future__ import annotations
import io
import json
from datetime import date

CHUNK_SIZE = 6000   # ~1500 tokens
MAX_PAGES = 20


def estimate_hours(topic_scores: list[dict], deadline: str) -> dict:
    days = max(1, (date.fromisoformat(deadline) - date.today()).days)
    total = sum(s["score"] * 0.5 for s in topic_scores)
    return {"total_hours": round(total, 1), "daily_budget": round(total / days, 1)}


def chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split text into ~size-char chunks, breaking at newlines where possible."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start:
                end = nl
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


async def run_pdf_ingestion(study_set_id: str, filename: str, content: bytes) -> None:
    import asyncio
    from pypdf import PdfReader
    from core.db import insert_file, insert_file_chunks, update_file_status
    from core.progress import push

    file_id = None
    try:
        await push(study_set_id, {"type": "task_progress", "stage": "ingestion", "done": False})
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        chunks = chunk_text(text)
        file_id = await insert_file(study_set_id, filename, text, len(reader.pages))  # status='processing'
        await insert_file_chunks(file_id, study_set_id, chunks)
        await update_file_status(file_id, "complete")
        await push(study_set_id, {"type": "task_progress", "stage": "ingestion", "done": True})
        asyncio.create_task(run_analyze(study_set_id))
    except Exception as e:
        if file_id:
            await update_file_status(file_id, "failed")
        await push(study_set_id, {"type": "task_progress", "stage": "ingestion", "done": True, "error": str(e)})



async def run_analyze(study_set_id: str) -> None:
    import asyncio
    from openai import AsyncOpenAI
    from core.db import delete_study_plan_data, delete_topic_scores, get_all_chunks, insert_topic_scores
    from core.progress import push

    try:
        await push(study_set_id, {"type": "task_progress", "stage": "weak_topic", "done": False})
        await delete_study_plan_data(study_set_id)
        await delete_topic_scores(study_set_id)
        text_chunks = await get_all_chunks(study_set_id)
        if not text_chunks:
            await push(study_set_id, {"type": "task_progress", "stage": "weak_topic", "done": True})
            return

        combined = "\n\n---\n\n".join(text_chunks[:20])[:8000]
        client = AsyncOpenAI()
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    "Analyze these study materials and identify the main topics. "
                    "Score each topic 1-10 for complexity/difficulty (10 = hardest). "
                    'Return JSON: {"topics": [{"topic": "...", "score": 7, "reason": "one sentence"}]}\n\n'
                    f"Materials:\n{combined}"
                ),
            }],
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        await insert_topic_scores(study_set_id, data.get("topics", []))
        await push(study_set_id, {"type": "task_progress", "stage": "weak_topic", "done": True})
        asyncio.create_task(run_study_plan(study_set_id))
    except Exception as e:
        await push(study_set_id, {"type": "task_progress", "stage": "weak_topic", "done": True, "error": str(e)})


async def run_study_plan(study_set_id: str) -> None:
    from openai import AsyncOpenAI
    from core.db import get_all_chunks, get_topic_scores, insert_flashcards, insert_quiz, insert_study_guide
    from core.progress import push

    try:
        await push(study_set_id, {"type": "task_progress", "stage": "study_plan", "done": False})
        scores = await get_topic_scores(study_set_id)
        text_chunks = await get_all_chunks(study_set_id)
        if not scores or not text_chunks:
            await push(study_set_id, {"type": "task_progress", "stage": "study_plan", "done": True})
            return

        topics_summary = "\n".join(
            f"- {s['topic']} (difficulty {s['score']}/10): {s['reason']}" for s in scores
        )
        combined = "\n\n---\n\n".join(text_chunks[:20])[:8000]
        weak = [s for s in scores if s["score"] >= 7]
        min_flashcards = max(10, len(weak) * 3)
        min_quiz_q = max(5, len(weak) * 2)

        client = AsyncOpenAI()
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": (
                    f"You are an expert educator. Based on these study materials and topic analysis, generate:\n\n"
                    f"Topics identified (higher score = harder):\n{topics_summary}\n\n"
                    f"Study materials excerpt:\n{combined}\n\n"
                    f"Generate ALL THREE of the following in a single JSON response:\n"
                    f"1. A comprehensive study guide in markdown (## headers per topic, bullet points, key concepts)\n"
                    f"2. At least {min_flashcards} flashcards (more for harder topics with score >= 7)\n"
                    f"3. At least {min_quiz_q} quiz questions covering weak topics (mix of MCQ and short answer)\n\n"
                    'Return JSON with this exact shape:\n'
                    '{"study_guide": "## Topic\\n...", '
                    '"flashcards": [{"front": "...", "back": "...", "topic": "..."}], '
                    '"quiz": [{"question": "...", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], '
                    '"answer": "A", "explanation": "..."}]}'
                ),
            }],
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        await insert_study_guide(study_set_id, data.get("study_guide", ""))
        await insert_flashcards(study_set_id, data.get("flashcards", []))
        await insert_quiz(study_set_id, data.get("quiz", []))
        await push(study_set_id, {"type": "task_progress", "stage": "study_plan", "done": True})
    except Exception as e:
        await push(study_set_id, {"type": "task_progress", "stage": "study_plan", "done": True, "error": str(e)})
