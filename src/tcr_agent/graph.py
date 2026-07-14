from __future__ import annotations

from typing import Any

from .agents.fix_agent import run_fix_agent
from .agents.llm_test_generation_agent import run_llm_test_generation_agent
from .agents.report_agent import run_report_agent
from .agents.test_agent import run_test_agent
from .agents.verify_agent import configured_max_fix_rounds, run_verify_agent
from .llm_gateway import LLMGateway
from .schemas import GraphState, ProjectInput


def build_graph():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("LangGraph is not installed. Run `python3 -m pip install -e .`.") from exc

    graph = StateGraph(GraphState)
    graph.add_node("llm_test_generation_agent", run_llm_test_generation_agent)
    graph.add_node("test_agent", run_test_agent)
    graph.add_node("report_agent", run_report_agent)
    graph.add_node("fix_agent", run_fix_agent)
    graph.add_node("verify_agent", run_verify_agent)
    graph.add_edge(START, "llm_test_generation_agent")
    graph.add_edge("llm_test_generation_agent", "test_agent")
    graph.add_edge("test_agent", "report_agent")
    graph.add_edge("report_agent", "fix_agent")
    graph.add_conditional_edges(
        "fix_agent",
        route_after_fix,
        {
            "verify": "verify_agent",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "verify_agent",
        route_after_verify,
        {
            "report": "report_agent",
            "end": END,
        },
    )
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


def run_direct(project: ProjectInput | dict[str, Any], gateway: LLMGateway | None = None) -> GraphState:
    project_input = project if isinstance(project, ProjectInput) else ProjectInput.from_dict(project)
    initial_state: GraphState = {
        "run_id": project_input.run_id,
        "project": project_input.to_dict(),
        "errors": [],
    }
    state = run_llm_test_generation_agent(initial_state, gateway=gateway)
    state = run_test_agent(state, gateway=gateway)
    while True:
        state = run_report_agent(state)
        state = run_fix_agent(state, gateway=gateway)
        if route_after_fix(state) != "verify":
            return state
        state = run_verify_agent(state)
        if route_after_verify(state) != "report":
            return state


def route_after_fix(state: GraphState) -> str:
    fix_result = state.get("fix_result", {})
    if fix_result.get("status") != "completed" or not fix_result.get("applied"):
        return "end"
    project = ProjectInput.from_dict(state["project"])
    max_rounds = configured_max_fix_rounds(project, state)
    if int(state.get("fix_round", 0)) >= max_rounds:
        return "end"
    return "verify"


def route_after_verify(state: GraphState) -> str:
    verify_result = state.get("verify_result", {})
    if verify_result.get("status") == "passed" or verify_result.get("passed"):
        return "end"
    if verify_result.get("status") == "skipped":
        return "end"
    project = ProjectInput.from_dict(state["project"])
    max_rounds = configured_max_fix_rounds(project, state)
    if int(state.get("fix_round", 0)) >= max_rounds:
        return "end"
    return "report"
