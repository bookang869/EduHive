from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END

from core.state import TutorState
from core.rag import retrieve_context
from agents.classification_agent import classification_agent
from agents.feynman_agent import feynman_agent
from agents.teacher_agent import teacher_agent
from agents.quiz_agent import quiz_agent

load_dotenv()


def router_check(state: TutorState) -> str:
    return state.get("current_agent", "classification_agent")


def _rag_query(state: TutorState) -> str:
    """Collect the last 3 HumanMessage contents as the RAG query."""
    msgs = []
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            msgs.append(msg.content)
            if len(msgs) == 3:
                break
    return "\n".join(reversed(msgs))


def make_rag_node(agent, inject_quiz=False):
    """Wrap a teaching agent: fetch RAG chunks + study guide (+ quiz for quiz_agent) when study_set_id is in state."""
    async def node(state: TutorState, config):
        import json as _json
        from core.db import get_study_guide, get_quiz
        updated = dict(state)
        updated["rag_context"] = None
        sid = state.get("study_set_id")
        if sid:
            query = _rag_query(state)
            if query:
                chunks = await retrieve_context(query, sid)
                if chunks:
                    updated["rag_context"] = "\n\n---\n\n".join(chunks)
            guide = await get_study_guide(sid)
            if guide:
                updated["rag_context"] = (updated["rag_context"] or "") + f"\n\n### Study Guide\n{guide}"
            if inject_quiz:
                quiz = await get_quiz(sid)
                if quiz:
                    updated["rag_context"] = (updated["rag_context"] or "") + (
                        f"\n\n### Prebuilt Quiz (id:{quiz['id']})\n"
                        + _json.dumps(quiz["questions"], indent=2)
                    )
        return await agent.ainvoke(updated, config)
    return node


def build_graph(checkpointer=None):
    graph_builder = StateGraph(TutorState)

    graph_builder.add_node("classification_agent", classification_agent, destinations=(
        "feynman_agent",
        "teacher_agent",
        "quiz_agent",
    ))
    graph_builder.add_node("feynman_agent", make_rag_node(feynman_agent))
    graph_builder.add_node("teacher_agent", make_rag_node(teacher_agent))
    graph_builder.add_node("quiz_agent", make_rag_node(quiz_agent, inject_quiz=True))

    graph_builder.add_conditional_edges(
        START,
        router_check,
        ["quiz_agent", "feynman_agent", "teacher_agent", "classification_agent"],
    )
    graph_builder.add_edge("classification_agent", END)

    if checkpointer:
        return graph_builder.compile(checkpointer=checkpointer)
    return graph_builder.compile()
