from __future__ import annotations

from typing import Any

from .agents.fix_agent import run_fix_agent
from .agents.report_agent import run_report_agent
from .agents.test_agent import run_test_agent
from .schemas import GraphState, ProjectInput


def build_graph():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("LangGraph is not installed. Run `python3 -m pip install -e .`.") from exc

    graph = StateGraph(GraphState)
    graph.add_node("test_agent", run_test_agent)
    graph.add_node("report_agent", run_report_agent)
    graph.add_node("fix_agent", run_fix_agent)
    graph.add_edge(START, "test_agent")
    graph.add_edge("test_agent", "report_agent")
    graph.add_edge("report_agent", "fix_agent")
    graph.add_edge("fix_agent", END)
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
    state = run_test_agent(initial_state)
    state = run_report_agent(state)
    return run_fix_agent(state)
