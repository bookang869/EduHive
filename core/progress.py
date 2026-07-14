import asyncio

# keyed by study_set_id; registered on WS connect, unregistered on disconnect
_queues: dict[str, asyncio.Queue] = {}


def register(study_set_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _queues[study_set_id] = q
    return q


def unregister(study_set_id: str) -> None:
    _queues.pop(study_set_id, None)


async def push(study_set_id: str, event: dict) -> None:
    q = _queues.get(study_set_id)
    if q:
        await q.put(event)
