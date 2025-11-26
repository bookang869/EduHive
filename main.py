from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END, MessagesState
from agents.classification_agent import classification_agent
from agents.feynman_agent import feynman_agent
from agents.teacher_agent import teacher_agent

# load the environment variables
load_dotenv()

class TutorState(MessagesState):
  current_agent: str

# router to determine which agent the user will be transferred to
def router_check(state: TutorState):
  current_agent = state.get("current_agent", "classification_agent")
  return current_agent

graph_builder = StateGraph(TutorState)

graph_builder.add_node("classification_agent", classification_agent, destinations=("teacher_agent", "feynman_agent"))
graph_builder.add_node("feynman_agent", feynman_agent)
graph_builder.add_node("teacher_agent", teacher_agent)

graph_builder.add_conditional_edges(
  START, 
  router_check, 
  [
    "feynman_agent", 
    "teacher_agent", 
    "classification_agent"
  ]
)
graph_builder.add_edge("classification_agent", END)

graph = graph_builder.compile()