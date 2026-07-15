import json
import unittest

from tcr_agent.graph import run_direct
from tcr_agent.llm_gateway import StaticLLMGateway
from tcr_agent.schemas import LLMResponse


BAD_MAIN = "def add(a, b):\n    return a - b\n"
FIXED_MAIN = "def add(a, b):\n    return a + b\n"
TEST_MAIN = "from main import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


class TestAgentProgress(unittest.TestCase):
    def test_progress_events_cover_fix_and_verify_round(self):
        events: list[dict] = []
        gateway = StaticLLMGateway(
            LLMResponse(
                content=json.dumps(
                    {
                        "fix_plan": "replace subtraction with addition",
                        "files": [
                            {
                                "file": "main.py",
                                "issue_ids": ["ISSUE-001"],
                                "content": FIXED_MAIN,
                            }
                        ],
                        "warnings": [],
                    }
                )
            )
        )

        result = run_direct(
            project(),
            gateway=gateway,
            progress_callback=lambda agent, status, state: events.append(
                {
                    "agent": agent,
                    "status": status,
                    "fix_round": int(state.get("fix_round", 0)),
                }
            ),
        )

        self.assertEqual(result["verify_result"]["status"], "passed")
        self.assertEqual(result["fix_round"], 1)
        self.assertIn(
            {"agent": "FixAgent", "status": "running", "fix_round": 0},
            events,
        )
        self.assertIn(
            {"agent": "VerifyAgent", "status": "running", "fix_round": 0},
            events,
        )
        self.assertIn(
            {"agent": "VerifyAgent", "status": "passed", "fix_round": 1},
            events,
        )

    def test_every_started_agent_has_a_terminal_event(self):
        events: list[tuple[str, str]] = []

        run_direct(
            project(auto_fix=False),
            progress_callback=lambda agent, status, _state: events.append((agent, status)),
        )

        started_agents = [agent for agent, status in events if status == "running"]
        for agent in started_agents:
            terminal_statuses = [
                status
                for event_agent, status in events
                if event_agent == agent and status != "running"
            ]
            self.assertTrue(terminal_statuses, f"{agent} did not emit a terminal event")


def project(auto_fix: bool = True) -> dict:
    return {
        "run_id": "progress_test",
        "language": "python",
        "files": [
            {"path": "main.py", "language": "python", "content": BAD_MAIN},
            {"path": "test_main.py", "language": "python", "content": TEST_MAIN},
        ],
        "config": {
            "lint_tools": ["py_compile"],
            "report_use_llm": False,
            "auto_fix": auto_fix,
            "max_fix_rounds": 2,
        },
    }


if __name__ == "__main__":
    unittest.main()
