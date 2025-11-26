from langgraph.types import Command
from langchain_core.tools import tool
from firecrawl import FirecrawlApp, ScrapeOptions
import re

# tool to transfer to an agent
# graph = Command
@tool
def transfer_to_agent(agent_name: str):
  """
  Transfer to the given agent.

  Args:
    agent_name: The name of the agent to transfer to ('quiz_agent', 'teacher_agent', 'feynman_agent')
  """

  # return f"Transfer to {agent_name} complete!"

  return Command(
    goto = agent_name,
    # currently, we are in a subgraph, so we need to transition to the parent graph
    graph = Command.PARENT
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

  # initialize the FireCrawlApp
  app = FirecrawlApp(api_key="FIRECRAWL_API_KEY")

  # search the web for information
  response = app.search(
    query=query,
    limit=5,  # number of results to return
    scrape_options=ScrapeOptions(
      formats=["markdown"], # format of the results
    )
  )

  # if the search is not successful, return an error
  if not response.success:
    return f"Error: {response.error}"

  cleaned_chunks = []

  for result in response.data:
    title = result["title"]
    url = result["url"]
    markdown = result["markdown"]

    # clean the markdown
    cleaned = re.sub(r"\\+|\n+", "", markdown).strip()
    cleaned = re.sub(r"\[[^\]]+\]\([^\)]+\)|https?://[^\s]+", "", cleaned)

    cleaned_result = {
      "title": title,
      "url": url,
      "markdown": markdown,
    }

    cleaned_chunks.append(cleaned_result)

  return cleaned_chunks