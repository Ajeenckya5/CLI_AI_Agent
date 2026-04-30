from __future__ import annotations

import unittest

from codecraft_agent.llm import OpenAICompatibleClient


class LLMClientTests(unittest.TestCase):
    def test_payload_omits_tools_when_empty(self) -> None:
        client = OpenAICompatibleClient(
            api_key="test-key",
            base_url="https://example.invalid/v1",
            model="fake-model",
        )

        payload = client._payload([{"role": "user", "content": "hi"}], [])  # noqa: SLF001

        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)

    def test_stream_tool_deltas_are_merged(self) -> None:
        client = OpenAICompatibleClient(
            api_key="test-key",
            base_url="https://example.invalid/v1",
            model="fake-model",
        )
        tool_calls: list[dict[str, object]] = []

        client._merge_tool_delta(  # noqa: SLF001
            tool_calls,
            {
                "index": 0,
                "id": "call_1",
                "type": "function",
                "function": {"name": "write_file", "arguments": '{"path":'},
            },
        )
        client._merge_tool_delta(  # noqa: SLF001
            tool_calls,
            {"index": 0, "function": {"arguments": '"README.md"}'}},
        )

        self.assertEqual(tool_calls[0]["id"], "call_1")
        self.assertEqual(tool_calls[0]["function"]["name"], "write_file")
        self.assertEqual(tool_calls[0]["function"]["arguments"], '{"path":"README.md"}')


if __name__ == "__main__":
    unittest.main()

