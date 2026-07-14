"""
Database integration tests for Phase 1b ingestion pipeline.
Requires DATABASE_URL in environment (loaded via conftest.py).
Run: uv run pytest tests/test_ingestion.py -v
"""
import os
import uuid

import pytest

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set")


@pytest.fixture
async def db_pool():
    """Per-test async pool — avoids event-loop mismatch with module-scoped fixtures."""
    from psycopg_pool import AsyncConnectionPool
    import core.db as db

    pool = AsyncConnectionPool(DATABASE_URL, open=False, min_size=1, max_size=3)
    await pool.open()
    db.init_pool(pool)
    yield pool
    await pool.close()
    db._pool = None
    db._client = None


@pytest.fixture
async def study_set(db_pool):
    """Create a throwaway study_set row and clean up after the test."""
    from core.db import create_study_set
    thread_id = f"test-{uuid.uuid4()}"
    sid = await create_study_set(thread_id)
    yield sid
    # delete children first (FK order) then parent
    async with db_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM topic_scores WHERE study_set_id = %s", (sid,))
            await cur.execute("DELETE FROM file_chunks WHERE study_set_id = %s", (sid,))
            await cur.execute("DELETE FROM web_chunks WHERE study_set_id = %s", (sid,))
            await cur.execute("DELETE FROM files WHERE study_set_id = %s", (sid,))
            await cur.execute("DELETE FROM study_sets WHERE id = %s", (sid,))
        await conn.commit()


async def test_create_study_set(db_pool):
    from core.db import create_study_set
    thread_id = f"test-{uuid.uuid4()}"
    sid = await create_study_set(thread_id)
    assert sid and len(sid) > 10

    # idempotent — same thread_id returns same id
    sid2 = await create_study_set(thread_id)
    assert sid == sid2

    async with db_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM study_sets WHERE id = %s", (sid,))
        await conn.commit()


async def test_insert_file_and_chunks(study_set):
    from core.db import insert_file, insert_file_chunks

    file_id = await insert_file(study_set, "test.pdf", "Hello world content.", 1)
    assert file_id and len(file_id) > 10

    await insert_file_chunks(file_id, study_set, ["Hello world content."])

    from core.db import _pool
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) FROM file_chunks WHERE study_set_id = %s", (study_set,))
            row = await cur.fetchone()
    assert row[0] == 1


async def test_insert_web_chunks(study_set):
    from core.db import insert_web_chunks, _pool

    await insert_web_chunks(study_set, "test query", ["Web content chunk one.", "Web content chunk two."])

    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) FROM web_chunks WHERE study_set_id = %s", (study_set,))
            row = await cur.fetchone()
    assert row[0] == 2


async def test_retrieve_context_after_insert(study_set):
    from core.db import insert_file, insert_file_chunks
    from core.rag import retrieve_context

    text = "Photosynthesis is how plants convert sunlight into energy."
    file_id = await insert_file(study_set, "bio.pdf", text, 1)
    await insert_file_chunks(file_id, study_set, [text])

    results = await retrieve_context("photosynthesis plants energy", study_set, k=5)
    assert len(results) >= 1
    assert "Photosynthesis" in results[0]


async def test_insert_topic_scores(study_set):
    from core.db import insert_topic_scores, _pool

    scores = [
        {"topic": "Algebra", "score": 7, "reason": "Complex formulas."},
        {"topic": "Calculus", "score": 9, "reason": "Abstract concepts."},
    ]
    await insert_topic_scores(study_set, scores)

    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) FROM topic_scores WHERE study_set_id = %s", (study_set,))
            row = await cur.fetchone()
    assert row[0] == 2


async def test_chunk_text():
    from core.ingestion import chunk_text
    text = "A" * 20000
    chunks = chunk_text(text, size=6000)
    assert len(chunks) >= 3
    assert all(len(c) <= 6000 for c in chunks)
