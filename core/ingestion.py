"""Background ingestion tasks: PDF, web search, weak-topic analysis."""
from __future__ import annotations
import io
import json
import os
import re

CHUNK_SIZE = 6000   # ~1500 tokens
MAX_PAGES = 20


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
    from pypdf import PdfReader
    from core.db import insert_file, insert_file_chunks
    from core.progress import push

    try:
        await push(study_set_id, {"type": "task_progress", "stage": "ingestion", "done": False})
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        chunks = chunk_text(text)
        file_id = await insert_file(study_set_id, filename, text, len(reader.pages))
        await insert_file_chunks(file_id, study_set_id, chunks)
        await push(study_set_id, {"type": "task_progress", "stage": "ingestion", "done": True})
    except Exception as e:
        await push(study_set_id, {"type": "task_progress", "stage": "ingestion", "done": True, "error": str(e)})


async def run_web_ingestion(study_set_id: str, query: str) -> None:
    from firecrawl import FirecrawlApp, ScrapeOptions
    from core.db import insert_web_chunks
    from core.progress import push

    try:
        await push(study_set_id, {"type": "task_progress", "stage": "ingestion", "done": False})
        app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
        response = app.search(query, limit=3, scrape_options=ScrapeOptions(formats=["markdown"]))
        if not response.success:
            return
        chunks: list[str] = []
        for result in response.data[:3]:
            md = re.sub(r"\[[^\]]+\]\([^)]+\)|https?://\S+", "", result.get("markdown", ""))
            chunks.extend(chunk_text(md[:10000]))
        await insert_web_chunks(study_set_id, query, chunks)
        await push(study_set_id, {"type": "task_progress", "stage": "ingestion", "done": True})
    except Exception as e:
        await push(study_set_id, {"type": "task_progress", "stage": "ingestion", "done": True, "error": str(e)})


async def run_analyze(study_set_id: str) -> None:
    from openai import AsyncOpenAI
    from core.db import get_all_chunks, insert_topic_scores
    from core.progress import push

    try:
        await push(study_set_id, {"type": "task_progress", "stage": "weak_topic", "done": False})
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
    except Exception as e:
        await push(study_set_id, {"type": "task_progress", "stage": "weak_topic", "done": True, "error": str(e)})
