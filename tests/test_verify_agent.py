import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tcr_agent.agents.test_agent import run_test_agent
from tcr_agent.agents.verify_agent import run_verify_agent
from tcr_agent.graph import run_direct
from tcr_agent.llm_gateway import StaticLLMGateway
from tcr_agent.schemas import LLMRequest, LLMResponse


BAD_MAIN = "def add(a, b):\n    return a - b\n"
WRONG_MAIN = "def add(a, b):\n    return 0\n"
FIXED_MAIN = "def add(a, b):\n    return a + b\n"
TEST_MAIN = "from main import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


class TestVerifyAgent(unittest.TestCase):
    def test_verify_agent_runs_against_fixed_workspace(self):
        state = make_tested_state()
        workspace = Path(state["test_result"]["workspace_dir"])
        (workspace / "main.py").write_text(FIXED_MAIN, encoding="utf-8")
        state["fix_result"] = applied_fix_result(workspace)

        state = run_verify_agent(state)

        self.assertEqual(state["verify_result"]["status"], "passed")
        self.assertTrue(state["verify_result"]["passed"])
        self.assertEqual(state["verify_result"]["round"], 1)
        self.assertEqual(state["test_result"]["agent"], "VerifyAgent")
        self.assertEqual(state["test_history"][0]["agent"], "TestAgent")

    def test_verify_agent_fails_when_fixed_workspace_still_fails(self):
        state = make_tested_state()
        workspace = Path(state["test_result"]["workspace_dir"])
        (workspace / "main.py").write_text(WRONG_MAIN, encoding="utf-8")
        state["fix_result"] = applied_fix_result(workspace)

        state = run_verify_agent(state)

        self.assertEqual(state["verify_result"]["status"], "failed")
        self.assertFalse(state["verify_result"]["passed"])
        self.assertEqual(state["test_result"]["status"], "failed")

    def test_run_direct_stops_after_verified_fix(self):
        gateway = StaticLLMGateway(LLMResponse(content=fix_response(FIXED_MAIN)))

        state = run_direct(project(max_fix_rounds=2), gateway=gateway)

        self.assertEqual(state["fix_round"], 1)
        self.assertEqual(state["verify_result"]["status"], "passed")
        self.assertEqual(state["test_history"][0]["status"], "failed")
        self.assertEqual(len(state["fix_history"]), 1)

    def test_run_direct_loops_until_second_fix_passes(self):
        gateway = SequenceLLMGateway(
            [
                LLMResponse(content=fix_response(WRONG_MAIN)),
                LLMResponse(content=fix_response(FIXED_MAIN)),
            ]
        )

        state = run_direct(project(max_fix_rounds=2), gateway=gateway)

        self.assertEqual(state["fix_round"], 2)
        self.assertEqual(state["verify_result"]["status"], "passed")
        self.assertEqual(len(state["verify_history"]), 2)
        self.assertEqual(len(gateway.requests), 2)

    def test_run_direct_stops_at_max_fix_rounds(self):
        gateway = StaticLLMGateway(LLMResponse(content=fix_response(WRONG_MAIN)))

        state = run_direct(project(max_fix_rounds=1), gateway=gateway)

        self.assertEqual(state["fix_round"], 1)
        self.assertEqual(state["verify_result"]["status"], "failed")
        self.assertEqual(len(state["verify_history"]), 1)
        self.assertEqual(len(gateway.requests), 1)

    def test_run_direct_does_not_verify_when_fix_skips(self):
        gateway = StaticLLMGateway(LLMResponse(content=fix_response(FIXED_MAIN)))

        state = run_direct(project(auto_fix=False), gateway=gateway)

        self.assertNotIn("verify_result", state)
        self.assertEqual(state["fix_result"]["status"], "skipped")
        self.assertEqual(len(gateway.requests), 0)


class SequenceLLMGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[LLMRequest] = []

    def chat(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("No more LLM responses configured")
        return self.responses.pop(0)


def make_tested_state():
    return run_test_agent({"run_id": "verify_unit", "project": project(), "errors": []})


def project(max_fix_rounds=2, auto_fix=True):
    return {
        "run_id": "verify_unit",
        "language": "python",
        "files": [
            {"path": "main.py", "language": "python", "content": BAD_MAIN},
            {"path": "test_main.py", "language": "python", "content": TEST_MAIN},
        ],
        "config": {
            "lint_tools": ["py_compile"],
            "report_use_llm": False,
            "auto_fix": auto_fix,
            "max_fix_rounds": max_fix_rounds,
        },
    }


def applied_fix_result(workspace: Path):
    return {
        "agent": "FixAgent",
        "status": "completed",
        "llm_used": True,
        "applied": True,
        "workspace_dir": str(workspace),
        "target_issue_ids": ["ISSUE-001"],
        "fix_plan": "fix",
        "patches": [],
        "warnings": [],
    }


def fix_response(content: str):
    return json.dumps(
        {
            "fix_plan": "fix add",
            "files": [{"file": "main.py", "issue_ids": ["ISSUE-001"], "content": content}],
            "warnings": [],
        }
    )


if __name__ == "__main__":
    unittest.main()
