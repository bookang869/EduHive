from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from .models import AgentRequest, AgentResponse
from .websocket_manager import manager
from auth.throttling import apply_rate_limit
from mangum import Mangum
from contextlib import asynccontextmanager
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import uuid
from pathlib import Path

# import .env variables
load_dotenv()

from core.graph import build_graph # noqa: E402

# Database path for persistent conversation storage
db_path = Path(__file__).parent.parent / "memory.db"

@asynccontextmanager
async def lifespan(app: FastAPI):
  """
  Manage application lifecycle with AsyncSqliteSaver context.
  This ensures the checkpointer is properly initialized and cleaned up.
  """
  # Enter AsyncSqliteSaver context manager
  async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
    # Initialize database tables
    await checkpointer.setup()
    
    # Build and compile graph with persistent checkpointer
    graph = build_graph(checkpointer=checkpointer)
    
    # Store graph and checkpointer in app state for use in endpoints
    app.state.graph = graph
    app.state.checkpointer = checkpointer
    
    # Yield control - FastAPI will serve requests now
    yield
    
    # Cleanup happens automatically when exiting the async with block

app = FastAPI(lifespan=lifespan)
# Mangum is a library for deploying FastAPI applications to AWS Lambda
handler = Mangum(app)

frontend_dir = Path(__file__).parent.parent / "frontend"
static_dir = frontend_dir / "static"

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# --- REST API Endpoints ---
@app.get("/")
async def root():
  return FileResponse(frontend_dir / "index.html")

@app.get("/health")
async def health_check():
  """Health check endpoint to verify API is running."""
  try:
    checks = {
      "status": "healthy",
      "graph_available": False,
      "checkpoint_available": False,
      "checkpoint_type": "sqlite"
    }

    graph = getattr(app.state, "graph", None)
    if graph is not None:
      checks["graph_available"] = True

      if hasattr(graph, "checkpointer") and graph.checkpointer is not None:
        checks["checkpoint_available"] = True

    if not checks["graph_available"] or not checks["checkpoint_available"]:
      checks["status"] = "degraded" 
      raise HTTPException(status_code=503, detail=checks)
    return checks
  except Exception as e:
    raise HTTPException(status_code=503, detail=f"Unhealthy: {str(e)}")

@app.post("/chat")
async def chat_endpoint(request: AgentRequest) -> AgentResponse:
  """
  Chat endpoint with session persistence

  - If session_id is provided, resume the conversation from that session
  - If session_id is not provided, create a new session
  - All converstaion history is automatically loaded from SQLite checkpoint
  """
  try:
    # generate a new or use existing session ID
    session_id = request.session_id or str(uuid.uuid4())

    # apply rate limit to the session ID
    apply_rate_limit(session_id)

    # create LangGraph config with session ID for checkpointing
    config = {"configurable": {"thread_id": session_id}}

    # create a human message from the user's prompt
    prompt = HumanMessage(content=request.prompt)

    # Get graph from app state
    graph = app.state.graph

    # invoke the graph with the human message and config (async)
    result = await graph.ainvoke({"messages": [prompt]}, config=config)

    messages = result.get("messages", [])
    if not messages:
      raise HTTPException(status_code=500, detail="No response generated")

    # get the last message (AI response)
    response = messages[-1].content

    # return the response with the session ID
    return AgentResponse(response=response, session_id=session_id)
    
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

#--- WebSocket Endpoint ---
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
  # Accept the WebSocket connection
  await manager.connect(websocket)

  # fetch client_id from url or create one if not found
  client_id = websocket.query_params.get("client_id")
  if not client_id:
    client_id = str(uuid.uuid4())

  try:
    while True:
      # Wait for and receive text data from the client
      data = await websocket.receive_text()

      # create LangGraph config with session ID for checkpointing
      config = {"configurable": {"thread_id": session_id}}

      # create a human message from the user's prompt
      prompt = HumanMessage(content=data)

      # Get graph from app state
      graph = app.state.graph

      # invoke the graph with the human message and config (async)
      result = await graph.ainvoke({"messages": [prompt]}, config=config)

      messages = result.get("messages", [])
      if not messages:
        raise HTTPException(status_code=500, detail="No response generated")

      # get the last message (AI response)
      response = messages[-1].content

      await manager.send_personal_message(response, websocket)
      await manager.broadcast(f"{client_id}: {data}", skip=websocket)
      await manager.broadcast(f"{response}", skip=websocket)
  except WebSocketDisconnect:
    manager.disconnect(websocket)
    await manager.broadcast(f"{client_id} has left {session_id}.")