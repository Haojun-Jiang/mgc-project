import copy
import json
import sys
import unittest
from pathlib import Path

from tcr_agent.graph import run_direct


ROOT = Path(__file__).resolve().parents[1]


class TestDemoExamples(unittest.TestCase):
    def test_passing_example_has_green_report(self):
        state = run_direct(load_project("python_passing"))

        self.assertEqual(state["test_result"]["status"], "passed")
        self.assertEqual(state["test_result"]["test_results"][0]["status"], "passed")
        self.assertEqual(state["report_result"]["risk_level"], "info")
        self.assertFalse(state["report_result"]["should_fix"])

    def test_syntax_error_example_reports_compliance_failure(self):
        state = run_direct(load_project("python_syntax_error"))

        self.assertEqual(state["test_result"]["status"], "failed")
        self.assertEqual(state["test_result"]["test_results"][0]["tool"], "static_only")
        compile_result = state["test_result"]["compliance_results"][0]
        self.assertEqual(compile_result["tool"], "py_compile")
        self.assertEqual(compile_result["status"], "failed")
        self.assertEqual(state["report_result"]["risk_level"], "high")

    def test_multi_file_example_reports_user_test_failures(self):
        state = run_direct(load_project("python_multi_file"))

        summary = state["test_result"]["test_results"][0]
        self.assertEqual(state["test_result"]["status"], "failed")
        self.assertEqual(summary["test_mode"], "user_test")
        self.assertEqual(summary["failed"], 2)
        self.assertEqual(state["report_result"]["risk_level"], "high")

    def test_custom_command_example_uses_command_test_mode(self):
        project = load_project("python_custom_command")
        project["config"]["test_command"] = [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-p",
            "check_*.py",
            "-v",
        ]

        state = run_direct(project)

        summary = state["test_result"]["test_results"][0]
        self.assertEqual(state["test_result"]["status"], "passed")
        self.assertEqual(summary["test_mode"], "command_test")
        self.assertEqual(summary["oracle_source"], "command")
        self.assertEqual(summary["total"], 2)


def load_project(name):
    data = json.loads((ROOT / "examples" / name / "project.json").read_text(encoding="utf-8"))
    return copy.deepcopy(data)


if __name__ == "__main__":
    unittest.main()
