from __future__ import annotations

import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from typing import Any

from codecraft_agent.agent import Agent
from codecraft_agent.config import AgentConfig
from codecraft_agent.ui import Console


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps(
                                {"path": "hello.txt", "content": "created by tool call\n"}
                            ),
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "Created hello.txt."}


class FakeStreamingClient:
    def chat_stream(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], on_delta=None) -> dict[str, Any]:
        if on_delta:
            on_delta("hello")
            on_delta(" world")
        return {"role": "assistant", "content": "hello world"}


class AgentLoopTests(unittest.TestCase):
    def test_agent_executes_function_call_and_returns_final_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            config = AgentConfig(
                workspace=workspace,
                provider="xai",
                model="fake-model",
                base_url="https://example.invalid/v1",
                api_key="test-key",
                api_key_env="XAI_API_KEY",
                auto_approve=True,
                color=False,
                stream=False,
            )
            agent = Agent(config, Console(color=False))
            agent.client = FakeClient()  # type: ignore[assignment]

            with contextlib.redirect_stdout(io.StringIO()):
                answer = agent.run("create a file")

            self.assertEqual(answer, "Created hello.txt.")
            self.assertEqual((workspace / "hello.txt").read_text(), "created by tool call\n")

    def test_agent_streams_final_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(
                workspace=Path(tmp),
                provider="xai",
                model="fake-model",
                base_url="https://example.invalid/v1",
                api_key="test-key",
                api_key_env="XAI_API_KEY",
                auto_approve=True,
                color=False,
                stream=True,
            )
            agent = Agent(config, Console(color=False))
            agent.client = FakeStreamingClient()  # type: ignore[assignment]

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                answer = agent.run("say hello")

            self.assertEqual(answer, "hello world")
            self.assertTrue(agent.last_response_streamed)
            self.assertIn("hello world", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
