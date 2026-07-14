import asyncio
import re
import os
from typing import Annotated

from firecrawl import FirecrawlApp, ScrapeOptions
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

@tool
def store_research_topic(
    topic: str,
    state: Annotated[dict, InjectedState()],
    tool_call_id: Annotated[str, InjectedToolCallId()],
) -> Command:
    """Mark a topic as already-researched so no agent re-searches it after a handoff."""
    current: list[str] = list(state.get("researched_topics") or [])
    if topic not in current:
        current.append(topic)
    return Command(update={
        "researched_topics": current,
        "messages": [ToolMessage(content="Stored.", tool_call_id=tool_call_id)],
    })


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
async def trigger_web_ingestion(
    topic: str,
    state: Annotated[dict, InjectedState()],
    tool_call_id: Annotated[str, InjectedToolCallId()],
) -> Command:
    """Trigger background web search ingestion for the identified topic. Call after Phase 1."""
    study_set_id = state.get("study_set_id")
    if study_set_id:
        from core.ingestion import run_web_ingestion
        asyncio.create_task(run_web_ingestion(study_set_id, topic))
    return Command(update={
        "messages": [ToolMessage(content="Web ingestion started.", tool_call_id=tool_call_id)],
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
  
@tool
def web_search_tool(query: str):
  """
  Web Search Tool to search the web for information.

  Args:
    query: The query to search the web for.

  Returns:
    A list of search results with the website content in Markdown (.md) format.
  """

  MAX_RESULTS = 3           # hard cap on how many pages we return
  MAX_CHARS_RESULT = 5000   # char cap per page (~1500-2500 tokens)

  # initialize the FireCrawlApp
  app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))

  # search the web for information
  response = app.search(
    query=query,
    limit=MAX_RESULTS,
    scrape_options=ScrapeOptions(
      formats=["markdown"], # format of the results
    )
  )

  # if the search is not successful, return an error
  if not response.success:
    return f"Error: {response.error}"

  cleaned_chunks = []

  for result in response.data[:MAX_RESULTS]:
    title = result["title"]
    url = result["url"]
    markdown = result["markdown"]

    cleaned = markdown

    # clean the markdown
    cleaned = re.sub(r"\[[^\]]+\]\([^)]+\)|https?://\S+", "", cleaned)

    # truncate the markdown to the maximum number of characters
    truncated = cleaned[:MAX_CHARS_RESULT].strip()

    cleaned_result = {
      "title": title,
      "url": url,
      "markdown": truncated,
    }

    cleaned_chunks.append(cleaned_result)

  return cleaned_chunks