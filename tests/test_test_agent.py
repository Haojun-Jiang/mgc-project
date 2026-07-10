import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tcr_agent.agents.report_agent import run_report_agent
from tcr_agent.agents.test_agent import run_test_agent
from tcr_agent.graph import run_direct
from tcr_agent.llm_gateway import StaticLLMGateway
from tcr_agent.schemas import LLMResponse, ProjectInput
from tcr_agent.tools import resolve_test_command


class TestTestAgent(unittest.TestCase):
    def test_default_test_command_uses_current_interpreter(self):
        project = {
            "run_id": "interpreter_test",
            "language": "python",
            "files": [{"path": "main.py", "content": "x = 1\n"}],
            "config": {},
        }
        command = resolve_test_command(ProjectInput.from_dict(project))
        self.assertEqual(command[0], sys.executable)

    def test_detects_unittest_failure(self):
        state = run_direct(
            {
                "run_id": "unit_test_failure",
                "language": "python",
                "files": [
                    {"path": "main.py", "content": "def add(a, b):\n    return a - b\n"},
                    {
                        "path": "test_main.py",
                        "content": (
                            "import unittest\n"
                            "from main import add\n\n"
                            "class TestAdd(unittest.TestCase):\n"
                            "    def test_add(self):\n"
                            "        self.assertEqual(add(1, 2), 3)\n"
                        ),
                    },
                ],
                "config": {"lint_tools": ["py_compile"], "report_use_llm": False},
            }
        )

        result = state["test_result"]
        self.assertEqual(result["agent"], "TestAgent")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["test_results"][0]["status"], "failed")
        self.assertEqual(result["compliance_results"][0]["status"], "passed")

    def test_ai_code_review_disabled_does_not_call_llm(self):
        gateway = StaticLLMGateway(LLMResponse(content='{"summary":"unused","issues":[]}'))
        state = run_test_agent(base_state({"ai_code_review_enabled": False}), gateway=gateway)

        self.assertEqual(len(gateway.requests), 0)
        llm_review = find_compliance(state, "llm_review")
        self.assertEqual(llm_review["status"], "skipped")
        self.assertEqual(state["test_result"]["status"], "passed")

    def test_ai_code_review_high_issue_fails_test_agent(self):
        gateway = StaticLLMGateway(
            LLMResponse(
                content=(
                    '{"summary":"发现高危逻辑错误","issues":[{"category":"bug","severity":"high",'
                    '"confidence":0.93,"file":"main.py","line":1,"line_end":2,'
                    '"message":"add 函数没有返回两数之和","evidence":"return a - b",'
                    '"root_cause":"实现使用了减法","recommendation":"改为 return a + b"}]}'
                )
            )
        )

        state = run_test_agent(base_state({"ai_code_review_enabled": True}), gateway=gateway)

        llm_review = find_compliance(state, "llm_review")
        self.assertEqual(llm_review["status"], "failed")
        self.assertEqual(llm_review["issues"][0]["severity"], "high")
        self.assertEqual(state["test_result"]["status"], "failed")

    def test_ai_code_review_medium_issue_enters_report_without_blocking(self):
        gateway = StaticLLMGateway(
            LLMResponse(
                content=(
                    '{"summary":"发现可维护性问题","issues":[{"category":"maintainability",'
                    '"severity":"medium","confidence":0.8,"file":"main.py","line":1,'
                    '"message":"函数缺少输入类型约束","evidence":"def add(a, b)",'
                    '"root_cause":"接口契约不清晰","recommendation":"增加类型标注或输入校验"}]}'
                )
            )
        )

        state = run_test_agent(base_state({"ai_code_review_enabled": True, "report_use_llm": False}), gateway=gateway)
        state = run_report_agent(state)

        llm_review = find_compliance(state, "llm_review")
        self.assertEqual(llm_review["status"], "completed")
        self.assertEqual(state["test_result"]["status"], "passed")
        self.assertEqual(state["report_result"]["issues"][0]["source"], "llm_review")
        self.assertEqual(state["report_result"]["issues"][0]["severity"], "medium")

    def test_ai_code_review_invalid_json_is_skipped(self):
        gateway = StaticLLMGateway(LLMResponse(content="not json"))

        state = run_test_agent(base_state({"ai_code_review_enabled": True}), gateway=gateway)

        llm_review = find_compliance(state, "llm_review")
        self.assertEqual(llm_review["status"], "skipped")
        self.assertTrue(llm_review["warnings"])
        self.assertEqual(state["test_result"]["status"], "passed")


def base_state(config):
    return {
        "run_id": "unit_ai_review",
        "project": {
            "run_id": "unit_ai_review",
            "language": "python",
            "files": [{"path": "main.py", "content": "def add(a, b):\n    return a + b\n"}],
            "config": {"lint_tools": ["py_compile"], **config},
        },
        "errors": [],
    }


def find_compliance(state, tool):
    for item in state["test_result"]["compliance_results"]:
        if item["tool"] == tool:
            return item
    raise AssertionError(f"compliance result not found: {tool}")


if __name__ == "__main__":
    unittest.main()
