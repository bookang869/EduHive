from langgraph.types import Command
from langchain_core.tools import tool

# tool to transfer to an agent
# graph = Command
@tool
def transfer_to_agent(agent_name: str):
  """
  Transfer to the given agent.

  Args:
    agent_name: The name of the agent to transfer to ('quiz_agent', 'teacher_agent', 'feynman_agent')
  """

  return Command(
    goto = agent_name,
    # currently, we are in a subgraph, so we need to transition to the parent graph
    graph = Command.PARENT
  )
  