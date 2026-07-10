import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tcr_agent.graph import run_direct


class TestTestAgent(unittest.TestCase):
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
                "config": {"lint_tools": ["py_compile"]},
            }
        )

        result = state["test_result"]
        self.assertEqual(result["agent"], "TestAgent")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["test_results"][0]["status"], "failed")
        self.assertEqual(result["compliance_results"][0]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
