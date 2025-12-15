from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
import uuid
import sys
from pathlib import Path

# import .env variables
load_dotenv()

# absolute path to the project root
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

from main import graph  # noqa: E402
from auth.throttling import apply_rate_limit  # noqa: E402

app = FastAPI()

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = new WebSocket("ws://localhost:8000/ws");
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""

# --- Pydantic Models ---
class AgentRequest(BaseModel):
  """Request model for agent invocation."""
  prompt: str
  session_id: str | None = None # optional session ID for conversation persistence

class AgentResponse(BaseModel):
  """Response model for agent invocation."""
  response: str
  session_id: str

# --- REST API Endpoints ---
@app.get("/")
async def root():
  return HTMLResponse(html)

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

    if graph is not None:
      checks["graph_available"] = True

      if hasattr(graph, "checkpointer") and graph.checkpointer is not None:
        checks["checkpoint_available"] = True

    if not checks["graph_available"] or not checks["checkpoint_available"]:
      checks["status"] = "degraded" 
      raise HTTPException(status_code=503, detail=checks)
    return checks
  except Exception as e:
    raise HTTPException(status_code=503, detial=f"Unhealthy: {str(e)}")

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
class ConnectionManager:
  def __init__(self):
    self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
      await websocket.accept()
      # add a new user to the list of active connections
      self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
      self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
      await websocket.send_text(message)
    
    async def broadcast(self, message: str, websocket: WebSocket):
      for connection in self.active_connections:
        await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/chat/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
  # 1. Accept the WebSocket connection
  await manager.connect(websocket)

  try:
    while True:
      data = await websocket.receive_text()

      # create LangGraph config with session ID for checkpointing
      config = {"configurable": {"thread_id": session_id}}

      # create a human message from the user's prompt
      prompt = HumanMessage(content=data)

      # invoke the graph with the human message and config (async)
      result = await graph.ainvoke({"messages": [prompt]}, config=config)

      messages = result.get("messages", [])
      if not messages:
        raise HTTPException(status_code=500, detail="No response generated")

      # get the last message (AI response)
      response = messages[-1].content

      await manager.send_personal_message(response, websocket)
      await manager.broadcast(f"Session {session_id} says: {data}")
  except WebSocketDisconnect:
    manager.disconnect(websocket)
    await manager.broadcast(f"Session {session_id} has left")

#--- Main ---    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="localhost", port=8000, reload=True)