import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tcr_agent.agents.report_agent import extract_json_object, generate_report
from tcr_agent.llm_gateway import StaticLLMGateway
from tcr_agent.schemas import LLMResponse, ProjectInput


class TestReportAgent(unittest.TestCase):
    def test_fallback_report_from_test_failure(self):
        project = ProjectInput.from_dict(
            {
                "run_id": "report_fallback",
                "language": "python",
                "files": [{"path": "main.py", "content": "def add(a, b): return a - b\n"}],
                "config": {"report_use_llm": False},
            }
        )
        report = generate_report(project, sample_test_result())

        self.assertEqual(report.agent, "ReportAgent")
        self.assertEqual(report.risk_level.value, "high")
        self.assertTrue(report.should_fix)
        self.assertEqual(report.issues[0].issue_id, "ISSUE-001")

    def test_llm_report_enriches_candidate_issue(self):
        project = ProjectInput.from_dict(
            {
                "run_id": "report_llm",
                "language": "python",
                "files": [{"path": "main.py", "content": "def add(a, b): return a - b\n"}],
                "config": {},
            }
        )
        gateway = StaticLLMGateway(
            LLMResponse(
                content=(
                    '{"summary":"add 函数逻辑错误导致测试失败","risk_level":"high","should_fix":true,'
                    '"issues":[{"issue_id":"ISSUE-001","source":"unittest","type":"logic_bug",'
                    '"severity":"high","confidence":0.96,"file":"main.py","line_start":1,"line_end":2,'
                    '"evidence":"AssertionError: -1 != 3","root_cause":"函数使用减法而非加法",'
                    '"recommendation":"将 return a - b 改为 return a + b"}]}'
                )
            )
        )

        report = generate_report(project, sample_test_result(), gateway=gateway)

        self.assertTrue(report.llm_used)
        self.assertEqual(report.summary, "add 函数逻辑错误导致测试失败")
        self.assertEqual(report.issues[0].type, "logic_bug")
        self.assertIn("return a + b", report.issues[0].recommendation)

    def test_extract_json_object_from_markdown(self):
        parsed = extract_json_object('```json\n{"summary":"ok","issues":[]}\n```')
        self.assertEqual(parsed["summary"], "ok")


def sample_test_result():
    return {
        "agent": "TestAgent",
        "status": "failed",
        "test_results": [
            {
                "tool": "unittest",
                "status": "failed",
                "failures": [
                    {
                        "test_id": "test_main.TestAdd.test_add",
                        "file": "test_main.py",
                        "line": 7,
                        "message": "AssertionError: -1 != 3",
                        "traceback": "Traceback ... AssertionError: -1 != 3",
                    }
                ],
            }
        ],
        "compliance_results": [{"tool": "py_compile", "status": "passed", "issues": []}],
    }


if __name__ == "__main__":
    unittest.main()
