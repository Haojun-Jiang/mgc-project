import sys
import unittest
from pathlib import Path
from tcr_agent.agents.report_agent import run_report_agent
from tcr_agent.agents.test_agent import run_test_agent
from tcr_agent.graph import run_direct
from tcr_agent.llm_gateway import StaticLLMGateway
from tcr_agent.schemas import LLMResponse, ProjectInput
from tcr_agent.tools import resolve_test_command, resolve_test_strategy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class TestTestAgent(unittest.TestCase):
    def test_default_test_command_uses_current_interpreter(self):
        project = {
            "run_id": "interpreter_test",
            "language": "python",
            "files": [
                {"path": "main.py", "content": "x = 1\n"},
                {"path": "test_main.py", "content": "def test_ok():\n    assert True\n"},
            ],
            "config": {},
        }
        command = resolve_test_command(ProjectInput.from_dict(project))
        self.assertEqual(command[0], sys.executable)

    def test_no_tests_defaults_to_static_only_without_llm(self):
        gateway = StaticLLMGateway(LLMResponse(content=generated_test_response()))
        state = run_test_agent(base_state({"llm_generated_tests_enabled": False}), gateway=gateway)

        summary = state["test_result"]["test_results"][0]
        self.assertEqual(len(gateway.requests), 0)
        self.assertEqual(resolve_test_strategy(ProjectInput.from_dict(state["project"])), "static_only")
        self.assertEqual(summary["tool"], "static_only")
        self.assertEqual(summary["status"], "skipped")
        self.assertEqual(summary["test_mode"], "static_only")
        self.assertEqual(summary["oracle_source"], "none")
        self.assertTrue(summary["warnings"])

    def test_llm_generated_tests_are_written_and_executed(self):
        gateway = StaticLLMGateway(LLMResponse(content=generated_test_response()))
        state = run_test_agent(
            base_state(
                {
                    "llm_generated_tests_enabled": True,
                    "requirement": "add(a, b) 应返回 a 与 b 的和",
                },
                code="def add(a, b):\n    return a - b\n",
            ),
            gateway=gateway,
        )

        summary = state["test_result"]["test_results"][0]
        generated_path = Path(summary["generated_test_ref"])
        self.assertEqual(len(gateway.requests), 1)
        self.assertEqual(summary["tool"], "llm_generated_tests")
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["test_mode"], "llm_generated_test")
        self.assertEqual(summary["oracle_source"], "llm_inferred")
        self.assertEqual(summary["confidence"], 0.9)
        self.assertTrue(generated_path.exists())
        self.assertIn("assert add(1, 2) == 3", generated_path.read_text(encoding="utf-8"))

    def test_llm_generated_tests_invalid_json_is_skipped(self):
        gateway = StaticLLMGateway(LLMResponse(content="not json"))
        state = run_test_agent(base_state({"llm_generated_tests_enabled": True}), gateway=gateway)

        summary = state["test_result"]["test_results"][0]
        self.assertEqual(summary["tool"], "llm_generated_tests")
        self.assertEqual(summary["status"], "skipped")
        self.assertTrue(summary["warnings"])
        self.assertEqual(state["test_result"]["compliance_results"][0]["status"], "passed")

    def test_llm_generated_tests_rejects_unsafe_path(self):
        gateway = StaticLLMGateway(
            LLMResponse(
                content=(
                    '{"inferred_behavior":"bad","confidence":0.7,'
                    '"test_file":"../test.py","test_code":"def test_bad():\\n    assert True\\n",'
                    '"warnings":[]}'
                )
            )
        )
        state = run_test_agent(base_state({"llm_generated_tests_enabled": True}), gateway=gateway)

        summary = state["test_result"]["test_results"][0]
        self.assertEqual(summary["status"], "skipped")
        self.assertIn("unsafe generated test file path", summary["warnings"][0])

    def test_user_tests_do_not_trigger_llm_generated_tests(self):
        gateway = StaticLLMGateway(LLMResponse(content=generated_test_response()))
        state = run_test_agent(
            {
                "run_id": "unit_user_tests",
                "project": {
                    "run_id": "unit_user_tests",
                    "language": "python",
                    "files": [
                        {"path": "main.py", "content": "def add(a, b):\n    return a + b\n"},
                        {"path": "test_main.py", "content": "from main import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"},
                    ],
                    "config": {"lint_tools": ["py_compile"], "llm_generated_tests_enabled": True},
                },
                "errors": [],
            },
            gateway=gateway,
        )

        summary = state["test_result"]["test_results"][0]
        self.assertEqual(len(gateway.requests), 0)
        self.assertEqual(summary["test_mode"], "user_test")
        self.assertEqual(summary["oracle_source"], "user_provided")

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


def base_state(config, code="def add(a, b):\n    return a + b\n"):
    return {
        "run_id": "unit_ai_review",
        "project": {
            "run_id": "unit_ai_review",
            "language": "python",
            "files": [{"path": "main.py", "content": code}],
            "config": {"lint_tools": ["py_compile"], **config},
        },
        "errors": [],
    }


def find_compliance(state, tool):
    for item in state["test_result"]["compliance_results"]:
        if item["tool"] == tool:
            return item
    raise AssertionError(f"compliance result not found: {tool}")


def generated_test_response():
    return (
        '{"inferred_behavior":"add(a, b) 应返回两个数之和","confidence":0.9,'
        '"test_file":"test_generated_llm.py",'
        '"test_code":"from main import add\\n\\n\\ndef test_add_generated():\\n    assert add(1, 2) == 3\\n",'
        '"warnings":[]}'
    )


if __name__ == "__main__":
    unittest.main()
