from __future__ import annotations
from openai import AsyncOpenAI

_pool = None
_client: AsyncOpenAI | None = None


def init_pool(pool) -> None:
    global _pool, _client
    _pool = pool
    _client = AsyncOpenAI()


async def setup_users_table() -> None:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    google_sub TEXT UNIQUE NOT NULL,
                    email TEXT NOT NULL,
                    name TEXT,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """)
        await conn.commit()


async def upsert_user(google_sub: str, email: str, name: str | None) -> None:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO users (google_sub, email, name)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (google_sub) DO UPDATE SET email = EXCLUDED.email, name = EXCLUDED.name""",
                (google_sub, email, name),
            )
        await conn.commit()


async def create_study_set(thread_id: str) -> str:
    """Create or return existing study_set for this WebSocket thread."""
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO study_sets (thread_id) VALUES (%s)
                   ON CONFLICT (thread_id) DO UPDATE SET thread_id = EXCLUDED.thread_id
                   RETURNING id""",
                (thread_id,),
            )
            row = await cur.fetchone()
        await conn.commit()
    return str(row[0])


async def insert_file(study_set_id: str, filename: str, extracted_text: str, page_count: int) -> str:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO files (study_set_id, storage_path, filename, extracted_text, page_count)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (study_set_id, f"uploads/{filename}", filename, extracted_text, page_count),
            )
            row = await cur.fetchone()
        await conn.commit()
    return str(row[0])


async def insert_file_chunks(file_id: str, study_set_id: str, chunks: list[str]) -> None:
    if not chunks:
        return
    resp = await _client.embeddings.create(model="text-embedding-3-small", input=chunks)
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            for i, (chunk, emb) in enumerate(zip(chunks, resp.data)):
                vec = "[" + ",".join(f"{v:.8f}" for v in emb.embedding) + "]"
                await cur.execute(
                    """INSERT INTO file_chunks (file_id, study_set_id, content, embedding, chunk_index)
                       VALUES (%s, %s, %s, %s::vector, %s)""",
                    (file_id, study_set_id, chunk, vec, i),
                )
        await conn.commit()



async def insert_topic_scores(study_set_id: str, scores: list[dict]) -> None:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM topic_scores WHERE study_set_id = %s", (study_set_id,))
            for s in scores:
                await cur.execute(
                    """INSERT INTO topic_scores (study_set_id, topic, score, reason)
                       VALUES (%s, %s, %s, %s)""",
                    (study_set_id, s["topic"], int(s["score"]), s.get("reason")),
                )
        await conn.commit()


async def get_topic_scores(study_set_id: str) -> list[dict]:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT topic, score, reason FROM topic_scores WHERE study_set_id = %s ORDER BY score DESC",
                (study_set_id,),
            )
            rows = await cur.fetchall()
    return [{"topic": r[0], "score": r[1], "reason": r[2]} for r in rows]


async def delete_topic_scores(study_set_id: str) -> None:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM topic_scores WHERE study_set_id = %s", (study_set_id,))
        await conn.commit()


async def delete_study_plan_data(study_set_id: str) -> None:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM study_guides WHERE study_set_id = %s", (study_set_id,))
            await cur.execute("DELETE FROM flashcards WHERE study_set_id = %s", (study_set_id,))
            await cur.execute(
                "DELETE FROM quizzes WHERE study_set_id = %s", (study_set_id,)
            )
        await conn.commit()


async def insert_study_guide(study_set_id: str, content_md: str) -> str:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO study_guides (study_set_id, content_md) VALUES (%s, %s) RETURNING id",
                (study_set_id, content_md),
            )
            row = await cur.fetchone()
        await conn.commit()
    return str(row[0])


async def insert_flashcards(study_set_id: str, cards: list[dict]) -> None:
    if not cards:
        return
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            for card in cards:
                await cur.execute(
                    "INSERT INTO flashcards (study_set_id, front, back, topic) VALUES (%s, %s, %s, %s)",
                    (study_set_id, card["front"], card["back"], card["topic"]),
                )
        await conn.commit()


async def insert_quiz(study_set_id: str, questions: list) -> str:
    import json as _json
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO quizzes (study_set_id, questions_json) VALUES (%s, %s::jsonb) RETURNING id",
                (study_set_id, _json.dumps(questions)),
            )
            row = await cur.fetchone()
        await conn.commit()
    return str(row[0])


async def get_study_guide(study_set_id: str) -> str | None:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT content_md FROM study_guides WHERE study_set_id = %s LIMIT 1",
                (study_set_id,),
            )
            row = await cur.fetchone()
    return row[0] if row else None


async def get_quiz(study_set_id: str) -> dict | None:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, questions_json FROM quizzes WHERE study_set_id = %s LIMIT 1",
                (study_set_id,),
            )
            row = await cur.fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "questions": row[1]}


async def get_study_materials(study_set_id: str) -> dict:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT content_md FROM study_guides WHERE study_set_id = %s LIMIT 1",
                (study_set_id,),
            )
            guide_row = await cur.fetchone()
            await cur.execute(
                "SELECT front, back, topic FROM flashcards WHERE study_set_id = %s",
                (study_set_id,),
            )
            fc_rows = await cur.fetchall()
            await cur.execute(
                "SELECT id, questions_json FROM quizzes WHERE study_set_id = %s LIMIT 1",
                (study_set_id,),
            )
            quiz_row = await cur.fetchone()
    return {
        "guide": guide_row[0] if guide_row else None,
        "flashcards": [{"front": r[0], "back": r[1], "topic": r[2]} for r in fc_rows],
        "quiz_id": str(quiz_row[0]) if quiz_row else None,
        "questions": quiz_row[1] if quiz_row else [],
    }


async def insert_quiz_attempt(quiz_id: str, score: int, wrong_topics: list[str]) -> None:
    import json as _json
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO quiz_attempts (quiz_id, score, wrong_topics) VALUES (%s, %s, %s::jsonb)",
                (quiz_id, score, _json.dumps(wrong_topics)),
            )
        await conn.commit()


async def get_all_chunks(study_set_id: str) -> list[str]:
    """Retrieve all text chunks for a study_set (used by weak-topic analysis)."""
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT content FROM file_chunks WHERE study_set_id = %s",
                (study_set_id,),
            )
            rows = await cur.fetchall()
    return [r[0] for r in rows]
