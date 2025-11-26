from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END, MessagesState
from agents.classification_agent import classification_agent
from agents.feynman_agent import feynman_agent
from agents.teacher_agent import teacher_agent

# load the environment variables
load_dotenv()

class TutorState(MessagesState):
  pass

graph_builder = StateGraph(TutorState)

graph_builder.add_node("classification_agent", classification_agent, destinations=["teacher_agent", "feynman_agent"])
graph_builder.add_node("feynman_agent", feynman_agent)
graph_builder.add_node("teacher_agent", teacher_agent)

graph_builder.add_edge(START, "classification_agent")

graph = graph_builder.compile()