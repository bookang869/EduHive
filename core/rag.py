from __future__ import annotations
import core.db as _db


async def retrieve_context(query: str, study_set_id: str, k: int = 5) -> list[str]:
    """Return up to k text chunks from file_chunks ordered by cosine similarity."""
    if _db._pool is None or not query.strip():
        return []

    resp = await _db._client.embeddings.create(model="text-embedding-3-small", input=query)
    vec_str = "[" + ",".join(f"{v:.8f}" for v in resp.data[0].embedding) + "]"

    sql = """
        SELECT content FROM file_chunks
        WHERE study_set_id = %s
        ORDER BY embedding <=> %s::vector LIMIT %s
    """

    async with _db._pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (study_set_id, vec_str, k))
            rows = await cur.fetchall()

    return [row[0] for row in rows]
