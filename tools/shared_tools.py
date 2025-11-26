from langgraph.types import Command
from langchain_core.tools import tool
from firecrawl import FirecrawlApp, ScrapeOptions
import re
import os

@tool
def transfer_to_agent(agent_name: str):
  """
  Transfer to the given agent.

  Args:
    agent_name: The name of the agent to transfer to, one of: 'teacher_agent', 'feynman_agent'
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