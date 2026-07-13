import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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
        from core.rag import init_pool

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

frontend_dir = Path(__file__).parent.parent / "frontend"
static_dir = frontend_dir / "static"

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    return FileResponse(frontend_dir / "index.html")


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
    client_id = websocket.query_params.get("client_id") or str(uuid.uuid4())

    try:
        while True:
            data = await websocket.receive_text()
            apply_rate_limit(session_id)
            config = {"configurable": {"thread_id": session_id}}
            result = await app.state.graph.ainvoke(
                {"messages": [HumanMessage(content=data)]}, config=config
            )
            messages = result.get("messages", [])
            if not messages:
                continue
            response = messages[-1].content
            await manager.send_personal_message(response, websocket)
            await manager.broadcast(f"{client_id}: {data}", skip=websocket)
            await manager.broadcast(response, skip=websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"{client_id} has left {session_id}.")
