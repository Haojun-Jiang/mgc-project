import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from tcr_agent.api import app


class TestAgentApi(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_runs_dir = os.environ.get("TCR_RUNS_DIR")
        os.environ["TCR_RUNS_DIR"] = self.tempdir.name
        self.client = TestClient(app)

    def tearDown(self):
        if self.old_runs_dir is None:
            os.environ.pop("TCR_RUNS_DIR", None)
        else:
            os.environ["TCR_RUNS_DIR"] = self.old_runs_dir
        self.tempdir.cleanup()

    def test_upload_source_builds_project_and_run_status(self):
        with patch("tcr_agent.api.run_graph", return_value=fake_result("ok")) as mock_run:
            response = self.client.post(
                "/runs",
                files=[("files", ("order_pricing.py", "def price():\n    return 1\n", "text/x-python"))],
                data={"requirement": "price should return 1"},
            )

        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run_id"]
        project = mock_run.call_args.args[0]
        self.assertEqual(project["run_id"], run_id)
        self.assertEqual(project["files"][0]["path"], "order_pricing.py")
        self.assertEqual(project["config"]["requirement"], "price should return 1")
        self.assertTrue(project["config"]["llm_generated_tests_enabled"])

        status_response = self.client.get(f"/runs/{run_id}")
        self.assertEqual(status_response.status_code, 200)
        status = status_response.json()
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["summary"], "ok")
        self.assertEqual(status["steps"][2]["agent"], "ReportAgent")

    def test_upload_user_test_disables_llm_test_generation(self):
        with patch("tcr_agent.api.run_graph", return_value=fake_result("ok")) as mock_run:
            response = self.client.post(
                "/runs",
                files=[
                    ("files", ("main.py", "def add(a, b):\n    return a + b\n", "text/x-python")),
                    ("files", ("test_main.py", "from main import add\n\ndef test_add():\n    assert add(1, 2) == 3\n", "text/x-python")),
                ],
            )

        self.assertEqual(response.status_code, 200)
        project = mock_run.call_args.args[0]
        self.assertFalse(project["config"]["llm_generated_tests_enabled"])

    def test_rejects_invalid_upload_names(self):
        text_response = self.client.post(
            "/runs",
            files=[("files", ("notes.txt", "hello", "text/plain"))],
        )
        self.assertEqual(text_response.status_code, 400)

        unsafe_response = self.client.post(
            "/runs",
            files=[("files", ("../evil.py", "x = 1\n", "text/x-python"))],
        )
        self.assertEqual(unsafe_response.status_code, 400)

    def test_report_patch_and_fixed_files_endpoints(self):
        workspace = Path(self.tempdir.name) / "workspace"
        workspace.mkdir()
        (workspace / "order_pricing.py").write_text("def fixed():\n    return True\n", encoding="utf-8")
        result = fake_result(
            "fixed",
            fix_result={
                "agent": "FixAgent",
                "status": "completed",
                "llm_used": True,
                "applied": True,
                "workspace_dir": str(workspace),
                "target_issue_ids": ["ISSUE-001"],
                "fix_plan": "fix",
                "patches": [
                    {
                        "file": "order_pricing.py",
                        "issue_ids": ["ISSUE-001"],
                        "change_type": "modify",
                        "diff": "--- a/order_pricing.py\n+++ b/order_pricing.py\n@@ -1 +1 @@\n-old\n+new\n",
                        "applied": True,
                        "error": "",
                    }
                ],
                "warnings": [],
            },
        )

        with patch("tcr_agent.api.run_graph", return_value=result):
            response = self.client.post(
                "/runs",
                files=[("files", ("order_pricing.py", "def fixed():\n    return False\n", "text/x-python"))],
            )

        run_id = response.json()["run_id"]
        report_response = self.client.get(f"/runs/{run_id}/report")
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.json()["summary"], "fixed")

        patch_response = self.client.get(f"/runs/{run_id}/diff.patch")
        self.assertEqual(patch_response.status_code, 200)
        self.assertIn("--- a/order_pricing.py", patch_response.text)

        artifact_response = self.client.get(f"/runs/{run_id}/artifacts/fix.patch")
        self.assertEqual(artifact_response.status_code, 200)
        self.assertIn("--- a/order_pricing.py", artifact_response.text)

        fixed_response = self.client.get(f"/runs/{run_id}/fixed-files")
        self.assertEqual(fixed_response.status_code, 200)
        self.assertEqual(fixed_response.json()["files"][0]["path"], "order_pricing.py")
        self.assertIn("return True", fixed_response.json()["files"][0]["content"])

    def test_status_steps_include_verify_agent(self):
        result = fake_result(
            "verified",
            verify_result={
                "agent": "VerifyAgent",
                "status": "passed",
                "passed": True,
                "round": 1,
                "max_rounds": 2,
                "workspace_dir": "",
                "test_result": {},
                "warnings": [],
            },
        )

        with patch("tcr_agent.api.run_graph", return_value=result):
            response = self.client.post(
                "/runs",
                files=[("files", ("order_pricing.py", "def fixed():\n    return True\n", "text/x-python"))],
            )

        run_id = response.json()["run_id"]
        status_response = self.client.get(f"/runs/{run_id}")
        self.assertEqual(status_response.status_code, 200)
        status = status_response.json()
        self.assertEqual(status["steps"][-1], {"agent": "VerifyAgent", "status": "passed"})
        self.assertEqual(status["result"]["verify_result"]["status"], "passed")


def fake_result(summary, fix_result=None, verify_result=None):
    return {
        "run_id": "placeholder",
        "project": {},
        "generated_test_result": {"agent": "LLMTestGenerationAgent", "status": "skipped"},
        "test_result": {"agent": "TestAgent", "status": "passed", "test_results": [], "compliance_results": []},
        "report_result": {
            "agent": "ReportAgent",
            "status": "completed",
            "summary": summary,
            "issues": [],
            "risk_level": "info",
            "should_fix": False,
            "llm_used": False,
            "warnings": [],
        },
        "fix_result": fix_result
        or {
            "agent": "FixAgent",
            "status": "skipped",
            "llm_used": False,
            "applied": False,
            "workspace_dir": "",
            "target_issue_ids": [],
            "fix_plan": "",
            "patches": [],
            "warnings": [],
        },
        "verify_result": verify_result or {},
        "errors": [],
    }


if __name__ == "__main__":
    unittest.main()
