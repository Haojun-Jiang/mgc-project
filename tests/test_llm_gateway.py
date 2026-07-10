import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tcr_agent.llm_gateway import LLMGatewayConfig, parse_bool, parse_openai_chat_response, parse_tool_arguments


class TestLLMGateway(unittest.TestCase):
    def test_parse_tool_call_response(self):
        response = parse_openai_chat_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "run_tests",
                                        "arguments": '{"command":["python3","-m","unittest"]}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        )

        self.assertEqual(response.content, "")
        self.assertEqual(response.tool_calls[0].name, "run_tests")
        self.assertEqual(response.tool_calls[0].arguments["command"][0], "python3")

    def test_parse_invalid_tool_arguments_keeps_raw(self):
        parsed = parse_tool_arguments("{not valid")
        self.assertIn("_raw", parsed)
        self.assertIn("_parse_error", parsed)

    def test_chat_completions_url_accepts_base_v1(self):
        config = LLMGatewayConfig(base_url="http://example.com/v1")
        self.assertEqual(config.chat_completions_url(), "http://example.com/v1/chat/completions")

    def test_parse_bool(self):
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("0"))
        self.assertTrue(parse_bool("true"))


if __name__ == "__main__":
    unittest.main()
