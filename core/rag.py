from __future__ import annotations
from openai import AsyncOpenAI

_pool = None
_client: AsyncOpenAI | None = None


def init_pool(pool) -> None:
    global _pool, _client
    _pool = pool
    _client = AsyncOpenAI()


async def retrieve_context(query: str, study_set_id: str, k: int = 5) -> list[str]:
    """Return up to k text chunks from file_chunks + web_chunks ordered by cosine similarity."""
    if _pool is None or not query.strip():
        return []

    resp = await _client.embeddings.create(model="text-embedding-3-small", input=query)
    vec_str = "[" + ",".join(f"{v:.8f}" for v in resp.data[0].embedding) + "]"

    sql = """
        (SELECT content, embedding <=> %s::vector AS dist
         FROM file_chunks WHERE study_set_id = %s ORDER BY dist LIMIT %s)
        UNION ALL
        (SELECT content, embedding <=> %s::vector AS dist
         FROM web_chunks WHERE study_set_id = %s ORDER BY dist LIMIT %s)
        ORDER BY dist LIMIT %s
    """

    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (vec_str, study_set_id, k, vec_str, study_set_id, k, k))
            rows = await cur.fetchall()

    return [row[0] for row in rows]
