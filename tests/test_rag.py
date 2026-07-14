import asyncio
import core.db as db
import core.rag as rag


async def test_no_pool_returns_empty():
    db._pool = None
    result = await rag.retrieve_context("what is photosynthesis", "fake-study-set-id")
    assert result == [], f"expected [], got {result}"


async def test_empty_query_returns_empty():
    db._pool = None
    result = await rag.retrieve_context("   ", "fake-study-set-id")
    assert result == [], f"expected [], got {result}"


if __name__ == "__main__":
    asyncio.run(test_no_pool_returns_empty())
    asyncio.run(test_empty_query_returns_empty())
    print("ok")
