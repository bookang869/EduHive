from itertools import starmap
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
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

app = FastAPI()

class AgentRequest(BaseModel):
  """Request model for agent invocation."""
  prompt: str
  session_id: str | None = None # optional session ID for conversation persistence

class AgentResponse(BaseModel):
  """Response model for agent invocation."""
  response: str
  session_id: str

@app.get("/")
async def root():
  return {"message": "EduHive API is running", "status": "healthy"}

@app.get("/health")
async def health_check():
  """Health check endpoint to verify API is running."""
  return {
    "status": "healthy",
    "graph_loaded": True,
    "checkpoint": "sqlite"
  }

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

    # create LangGraph config with session ID for checkpointing
    config = {"configurable": {"thread_id": session_id}}

    # create a human message from the user's prompt
    prompt = HumanMessage(content=request.prompt)

    # invoke the graph with the human message and config
    result = graph.invoke({"messages": [prompt]}, config=config)

    messages = result.get("messages", [])
    if not messages:
      raise HTTPException(status_code=500, detail="No response generated")

    # get the last message (AI response)
    response = messages[-1].content

    # return the response with the session ID
    return AgentResponse(response=response, session_id=session_id)
    
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)