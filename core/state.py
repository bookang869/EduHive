from typing import Optional
from langgraph.graph import MessagesState
from langgraph.prebuilt.chat_agent_executor import RemainingSteps


class TutorState(MessagesState):
    current_agent: str
    study_set_id: Optional[str]
    deadline: Optional[str]
    study_plan: Optional[str]
    rag_context: Optional[str]
    remaining_steps: RemainingSteps
