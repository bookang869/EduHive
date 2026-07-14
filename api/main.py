import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from mangum import Mangum

from .models import AgentRequest, AgentResponse
from .websocket_manager import manager
from auth.throttling import apply_rate_limit

load_dotenv()

from core.graph import build_graph  # noqa: E402

db_path = Path(__file__).parent.parent / "memory.db"
DEPLOYMENT_ENV = os.environ.get("DEPLOYMENT_ENV", "local")
DATABASE_URL = os.environ.get("DATABASE_URL")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DATABASE_URL:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool
        from core.db import init_pool

        pool = AsyncConnectionPool(DATABASE_URL, open=False)
        await pool.open()
        init_pool(pool)

        async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
            await checkpointer.setup()
            app.state.graph = build_graph(checkpointer=checkpointer)
            app.state.checkpointer = checkpointer
            app.state.checkpoint_type = "postgres"
            yield

        await pool.close()

    elif DEPLOYMENT_ENV == "lambda":
        from langgraph_checkpoint_dynamodb.saver import DynamoDBSaver

        checkpointer = DynamoDBSaver(
            checkpoints_table_name=os.environ.get("CHECKPOINTS_TABLE", "eduhive-checkpoints"),
            writes_table_name=os.environ.get("WRITES_TABLE", "eduhive-writes"),
            client_config={"region_name": os.environ.get("AWS_REGION", "us-west-2")},
        )
        app.state.graph = build_graph(checkpointer=checkpointer)
        app.state.checkpointer = checkpointer
        app.state.checkpoint_type = "dynamodb"
        yield

    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
            await checkpointer.setup()
            app.state.graph = build_graph(checkpointer=checkpointer)
            app.state.checkpointer = checkpointer
            app.state.checkpoint_type = "sqlite"
            yield


app = FastAPI(lifespan=lifespan)
handler = Mangum(app)

_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:8080").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .ingestion import router as ingestion_router  # noqa: E402
app.include_router(ingestion_router)


@app.get("/")
async def root():
    return {"service": "EduHive API", "docs": "/docs"}


@app.get("/health")
async def health_check():
    try:
        checks = {
            "status": "healthy",
            "graph_available": False,
            "checkpoint_available": False,
            "checkpoint_type": getattr(app.state, "checkpoint_type", "unknown"),
        }
        if getattr(app.state, "graph", None) is not None:
            checks["graph_available"] = True
        if getattr(app.state, "checkpointer", None) is not None:
            checks["checkpoint_available"] = True

        if not checks["graph_available"] or not checks["checkpoint_available"]:
            checks["status"] = "degraded"
            raise HTTPException(status_code=503, detail=checks)
        return checks
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unhealthy: {str(e)}")


@app.post("/chat")
async def chat_endpoint(request: AgentRequest) -> AgentResponse:
    try:
        session_id = request.session_id or str(uuid.uuid4())
        apply_rate_limit(session_id)
        config = {"configurable": {"thread_id": session_id}}
        result = await app.state.graph.ainvoke(
            {"messages": [HumanMessage(content=request.prompt)]}, config=config
        )
        messages = result.get("messages", [])
        if not messages:
            raise HTTPException(status_code=500, detail="No response generated")
        return AgentResponse(response=messages[-1].content, session_id=session_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(websocket)

    study_set_id: str | None = None
    if DATABASE_URL:
        from core.db import create_study_set
        study_set_id = await create_study_set(session_id)

    from core.progress import register, unregister
    progress_q = register(study_set_id) if study_set_id else None

    # handshake — client needs study_set_id before uploading PDFs
    await websocket.send_json({"type": "session", "study_set_id": study_set_id, "thread_id": session_id})

    try:
        while True:
            raw = await websocket.receive_text()
            apply_rate_limit(session_id)

            try:
                payload = json.loads(raw)
                message = payload.get("message", raw)
            except (json.JSONDecodeError, AttributeError):
                message = raw

            config = {"configurable": {"thread_id": session_id}}
            invoke_input: dict = {"messages": [HumanMessage(content=message)]}
            if study_set_id:
                invoke_input["study_set_id"] = study_set_id

            # signal that classification_agent is starting
            await websocket.send_json({"type": "agent_switch", "agent": "classification_agent"})

            async for event in app.state.graph.astream_events(invoke_input, config, version="v2"):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and chunk.content:
                        text = chunk.content
                        if isinstance(text, list):
                            text = "".join(
                                c.get("text", "") for c in text if isinstance(c, dict)
                            )
                        if text:
                            await websocket.send_json({"type": "token", "content": text})

                elif kind == "on_tool_start" and event.get("name") == "transfer_to_agent":
                    agent_name = (event["data"].get("input") or {}).get("agent_name", "")
                    if agent_name:
                        await websocket.send_json({"type": "agent_switch", "agent": agent_name})

                # drain any queued progress events after each LangGraph event
                if progress_q:
                    while not progress_q.empty():
                        await websocket.send_json(progress_q.get_nowait())

            # final drain after stream ends
            if progress_q:
                while not progress_q.empty():
                    await websocket.send_json(progress_q.get_nowait())

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
        if study_set_id:
            unregister(study_set_id)
