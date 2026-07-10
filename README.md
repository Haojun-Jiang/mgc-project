# TCR Agent Prototype

This workspace contains a minimal first step for a test-compliance-fix agent.

Current scope:

- shared schemas for project input, agent output, tool output, and LLM tool calls
- OpenAI-compatible tool definitions for future LLM loops
- a simple `TestAgent`
- a LangGraph entry point: `START -> TestAgent -> END`
- a direct fallback runner that works before LangGraph is installed

## Layout

```text
src/tcr_agent/
  schemas.py              Shared data contracts
  tool_defs.py            LLM-facing tool JSON schemas
  tools.py                Local sandbox command tools
  graph.py                LangGraph wiring
  cli.py                  JSON input runner
  agents/test_agent.py    First agent node
```

## Run the direct TestAgent path

This path only uses the Python standard library:

```bash
PYTHONPATH=src python3 -m tcr_agent.cli --input examples/python_bug/project.json --direct
```

## Run through LangGraph

Install dependencies first:

```bash
python3 -m pip install -e .
PYTHONPATH=src python3 -m tcr_agent.cli --input examples/python_bug/project.json
```

If `langgraph` is not installed, the CLI will explain how to install it.
