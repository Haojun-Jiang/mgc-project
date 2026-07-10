from __future__ import annotations

from typing import Any

from .agents.test_agent import run_test_agent
from .schemas import GraphState, ProjectInput


def build_graph():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("LangGraph is not installed. Run `python3 -m pip install -e .`.") from exc

    graph = StateGraph(GraphState)
    graph.add_node("test_agent", run_test_agent)
    graph.add_edge(START, "test_agent")
    graph.add_edge("test_agent", END)
    return graph.compile()


def run_graph(project: ProjectInput | dict[str, Any]) -> GraphState:
    project_input = project if isinstance(project, ProjectInput) else ProjectInput.from_dict(project)
    app = build_graph()
    initial_state: GraphState = {
        "run_id": project_input.run_id,
        "project": project_input.to_dict(),
        "errors": [],
    }
    return app.invoke(initial_state)


def run_direct(project: ProjectInput | dict[str, Any]) -> GraphState:
    project_input = project if isinstance(project, ProjectInput) else ProjectInput.from_dict(project)
    initial_state: GraphState = {
        "run_id": project_input.run_id,
        "project": project_input.to_dict(),
        "errors": [],
    }
    return run_test_agent(initial_state)
