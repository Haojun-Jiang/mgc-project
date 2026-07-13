import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tcr_agent.agents.fix_agent import run_fix_agent
from tcr_agent.agents.test_agent import run_test_agent
from tcr_agent.llm_gateway import StaticLLMGateway
from tcr_agent.schemas import LLMResponse


REPO_ROOT = Path(__file__).resolve().parents[1]
BAD_MAIN = "def add(a, b):\n    return a - b\n"
FIXED_MAIN = "def add(a, b):\n    return a + b\n"


class TestFixAgent(unittest.TestCase):
    def test_auto_fix_false_skips_without_llm(self):
        gateway = StaticLLMGateway(LLMResponse(content=fix_response()))
        state = make_state(config={"auto_fix": False})

        state = run_fix_agent(state, gateway=gateway)

        self.assertEqual(len(gateway.requests), 0)
        self.assertEqual(state["fix_result"]["status"], "skipped")
        self.assertFalse(state["fix_result"]["applied"])

    def test_report_should_fix_false_skips_without_llm(self):
        gateway = StaticLLMGateway(LLMResponse(content=fix_response()))
        state = make_state(config={"auto_fix": True}, should_fix=False)

        state = run_fix_agent(state, gateway=gateway)

        self.assertEqual(len(gateway.requests), 0)
        self.assertEqual(state["fix_result"]["status"], "skipped")

    def test_applies_fixed_file_to_workspace_only(self):
        example_path = REPO_ROOT / "examples" / "python_bug" / "main.py"
        original_example = example_path.read_text(encoding="utf-8")
        gateway = StaticLLMGateway(LLMResponse(content=fix_response()))
        state = make_state(config={"auto_fix": True}, code=original_example)

        state = run_fix_agent(state, gateway=gateway)

        result = state["fix_result"]
        workspace_main = Path(result["workspace_dir"]) / "main.py"
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["applied"])
        self.assertEqual(workspace_main.read_text(encoding="utf-8"), FIXED_MAIN)
        self.assertEqual(example_path.read_text(encoding="utf-8"), original_example)
        self.assertIn("return a + b", result["patches"][0]["diff"])

    def test_invalid_json_fails_without_writing_file(self):
        gateway = StaticLLMGateway(LLMResponse(content="not json"))
        state = make_state(config={"auto_fix": True})
        workspace_main = Path(state["test_result"]["workspace_dir"]) / "main.py"

        state = run_fix_agent(state, gateway=gateway)

        self.assertEqual(state["fix_result"]["status"], "failed")
        self.assertFalse(state["fix_result"]["applied"])
        self.assertEqual(workspace_main.read_text(encoding="utf-8"), BAD_MAIN)
        self.assertTrue(state["fix_result"]["warnings"])

    def test_rejects_unsafe_and_non_input_files(self):
        gateway = StaticLLMGateway(
            LLMResponse(
                content=(
                    '{"fix_plan":"bad paths","files":['
                    '{"file":"../evil.py","issue_ids":["ISSUE-001"],"content":"x = 1\\n"},'
                    '{"file":"other.py","issue_ids":["ISSUE-001"],"content":"x = 2\\n"}'
                    '],"warnings":[]}'
                )
            )
        )
        state = make_state(config={"auto_fix": True})

        state = run_fix_agent(state, gateway=gateway)

        result = state["fix_result"]
        errors = [patch["error"] for patch in result["patches"]]
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["applied"])
        self.assertTrue(any("unsafe file path" in error for error in errors))
        self.assertTrue(any("not part of project input" in error for error in errors))

    def test_medium_target_config_can_fix(self):
        gateway = StaticLLMGateway(LLMResponse(content=fix_response()))
        state = make_state(
            config={"auto_fix": True, "fix_target_severities": ["medium"]},
            severity="medium",
        )

        state = run_fix_agent(state, gateway=gateway)

        result = state["fix_result"]
        workspace_main = Path(result["workspace_dir"]) / "main.py"
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["applied"])
        self.assertEqual(workspace_main.read_text(encoding="utf-8"), FIXED_MAIN)


def make_state(config=None, code=BAD_MAIN, severity="high", file="main.py", should_fix=True):
    config = {"lint_tools": ["py_compile"], "report_use_llm": False, **(config or {})}
    project = {
        "run_id": "fix_agent_unit",
        "language": "python",
        "files": [{"path": "main.py", "language": "python", "content": code}],
        "config": config,
    }
    state = run_test_agent({"run_id": project["run_id"], "project": project, "errors": []})
    state["report_result"] = {
        "agent": "ReportAgent",
        "status": "completed",
        "summary": "add 函数逻辑错误",
        "risk_level": severity,
        "should_fix": should_fix,
        "llm_used": False,
        "warnings": [],
        "issues": [
            {
                "issue_id": "ISSUE-001",
                "source": "llm_review",
                "type": "bug",
                "severity": severity,
                "confidence": 0.95,
                "file": file,
                "line_start": 1,
                "line_end": 2,
                "evidence": "return a - b",
                "root_cause": "函数使用了减法",
                "recommendation": "改为 return a + b",
            }
        ],
    }
    return state


def fix_response():
    return (
        '{"fix_plan":"将 add 函数中的减法修正为加法",'
        '"files":[{"file":"main.py","issue_ids":["ISSUE-001"],'
        '"content":"def add(a, b):\\n    return a + b\\n"}],'
        '"warnings":[]}'
    )


if __name__ == "__main__":
    unittest.main()
