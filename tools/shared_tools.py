from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

@tool
def set_deadline(
    deadline: str,
    tool_call_id: Annotated[str, InjectedToolCallId()],
) -> Command:
    """Write the user's study deadline to state. deadline must be YYYY-MM-DD."""
    return Command(update={
        "deadline": deadline,
        "messages": [ToolMessage(content="Deadline set.", tool_call_id=tool_call_id)],
    })


@tool
def set_study_plan(
    plan: str,
    tool_call_id: Annotated[str, InjectedToolCallId()],
) -> Command:
    """Write the inline session study plan to state after Phase 3 assessment."""
    return Command(update={
        "study_plan": plan,
        "messages": [ToolMessage(content="Study plan set.", tool_call_id=tool_call_id)],
    })


@tool
def transfer_to_agent(agent_name: str):
  """
  Transfer to the given agent.

  Args:
    agent_name: The name of the agent to transfer to, one of: 'quiz_agent', 'teacher_agent', 'feynman_agent'
  """

  return Command(
    goto = agent_name,
    # currently, we are in a subgraph, so we need to transition to the parent graph
    graph = Command.PARENT,
    update = {
      "current_agent": agent_name
    }
  )
  
