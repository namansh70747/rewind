"""Third worked example: local LangGraph state replay; install .[integrations]."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from flightrecorder.boundary import Cassette, Session
from flightrecorder.integrations.langgraph import run_graph
from flightrecorder.replay import verify


class State(TypedDict):
    budget: int
    affordable: bool


def agent(session: Session, inner: object = None) -> str:
    graph = StateGraph(State)
    graph.add_node("check", lambda state: {"affordable": state["budget"] >= 420})
    graph.add_edge(START, "check")
    graph.add_edge("check", END)
    return run_graph(graph.compile(), {"budget": 500, "affordable": False}, session)


if __name__ == "__main__":
    session = Session("record")
    output = agent(session)
    cassette = Cassette(session.boundaries, session.chain, output)
    print(verify(cassette, agent, n=50))
