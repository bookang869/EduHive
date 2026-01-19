from pydantic import BaseModel

class AgentRequest(BaseModel):
  """Request model for agent invocation."""
  prompt: str
  session_id: str | None = None # optional session ID for conversation persistence

class AgentResponse(BaseModel):
  """Response model for agent invocation."""
  response: str
  session_id: str
  