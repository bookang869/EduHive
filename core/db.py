from __future__ import annotations
from openai import AsyncOpenAI

_pool = None
_client: AsyncOpenAI | None = None


def init_pool(pool) -> None:
    global _pool, _client
    _pool = pool
    _client = AsyncOpenAI()


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


async def insert_web_chunks(study_set_id: str, query: str, chunks: list[str]) -> None:
    if not chunks:
        return
    resp = await _client.embeddings.create(model="text-embedding-3-small", input=chunks)
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            for chunk, emb in zip(chunks, resp.data):
                vec = "[" + ",".join(f"{v:.8f}" for v in emb.embedding) + "]"
                await cur.execute(
                    """INSERT INTO web_chunks (study_set_id, query, content, embedding)
                       VALUES (%s, %s, %s, %s::vector)""",
                    (study_set_id, query, chunk, vec),
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


async def get_all_chunks(study_set_id: str) -> list[str]:
    """Retrieve all text chunks for a study_set (used by weak-topic analysis)."""
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT content FROM file_chunks WHERE study_set_id = %s
                   UNION ALL
                   SELECT content FROM web_chunks WHERE study_set_id = %s""",
                (study_set_id, study_set_id),
            )
            rows = await cur.fetchall()
    return [r[0] for r in rows]
