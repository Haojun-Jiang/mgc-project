# TCR Agent Prototype

This workspace contains a minimal first step for a test-compliance-fix agent.

Current scope:

- shared schemas for project input, agent output, tool output, and LLM tool calls
- an OpenAI-compatible `LLMGateway` abstraction for external model APIs
- OpenAI-compatible tool definitions for future LLM loops
- a simple `TestAgent`
- optional AI code review in `TestAgent` via `llm_review`
- a lightweight `ReportAgent` that turns test/compliance facts into a structured report
- a LangGraph entry point: `START -> TestAgent -> ReportAgent -> END`
- a direct fallback runner that works before LangGraph is installed

## Layout

```text
src/tcr_agent/
  schemas.py              Shared data contracts
  llm_gateway.py          OpenAI-compatible LLM gateway adapter
  tool_defs.py            LLM-facing tool JSON schemas
  tools.py                Local sandbox command tools
  graph.py                LangGraph wiring
  cli.py                  JSON input runner
  agents/test_agent.py    First agent node
  agents/report_agent.py  Structured report node
  templates/              Prompt templates
```

## Run the direct agent path

This path runs `TestAgent` and `ReportAgent` without requiring LangGraph:

```bash
PYTHONPATH=src python3 -m tcr_agent.cli --input examples/python_bug/project.json --direct
```

You can also use the root entrypoint:

```bash
python run.py --input examples/python_bug/project.json --direct
```

Or pass existing Python files directly:

```bash
python run.py --code examples/python_bug/main.py --test examples/python_bug/test_main.py --direct --no-report-llm
```

## Run through LangGraph

Install dependencies first:

```bash
python3 -m pip install -e .
PYTHONPATH=src python3 -m tcr_agent.cli --input examples/python_bug/project.json
```

If `langgraph` is not installed, the CLI will explain how to install it.

## LLM Gateway

Configure an OpenAI-compatible model gateway with environment variables:

```bash
cp .env.example .env
export LLM_GATEWAY_BASE_URL=http://your-llm-gateway.example.com/v1
export LLM_GATEWAY_API_KEY=replace-me
export LLM_GATEWAY_MODEL=company-qwen-coder
```

The gateway expects a `/chat/completions` endpoint. If `LLM_GATEWAY_BASE_URL`
already ends with `/chat/completions`, it will use that URL directly.

If your company network injects a self-signed TLS certificate during local
development, you can temporarily set:

```bash
export LLM_GATEWAY_VERIFY_SSL=false
```

Prefer installing the company CA certificate for normal use.

## AI Code Review

`TestAgent` can optionally run a lightweight LLM code review and expose the
result as a compliance check named `llm_review`.

```json
{
  "config": {
    "ai_code_review_enabled": true,
    "ai_code_review_max_chars": 12000,
    "ai_code_review_max_tokens": 2048
  }
}
```

By default this is disabled. `critical` and `high` review issues fail
`TestAgent`; `medium`, `low`, and `info` issues enter the report without
blocking.
