from __future__ import annotations

import json
from typing import Any

from .config import AgentConfig
from .llm import LLMError, OpenAICompatibleClient
from .tools import ToolError, ToolRegistry
from .ui import Console


SYSTEM_PROMPT = """You are CodeCraft Agent, a CLI coding assistant.

Work like a careful senior engineer:
- Inspect files before editing when context matters.
- Use tools to read, search, create, edit, and test code in the workspace.
- Keep changes scoped to the user's request.
- Prefer small, targeted edits over broad rewrites.
- After modifying code, run relevant checks when practical.
- Explain the result clearly and mention any tests or commands run.

Tool rules:
- All paths are relative to the configured workspace.
- Use read_file before replace_in_file unless the exact old text is already known.
- Use run_command for tests, linters, build steps, and project inspection.
- Do not claim a tool action succeeded unless the tool result says it did.
"""


class Agent:
    def __init__(self, config: AgentConfig, console: Console) -> None:
        self.config = config
        self.console = console
        self.client = OpenAICompatibleClient(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            temperature=config.temperature,
        )
        self.tools = ToolRegistry(config.workspace, default_timeout=config.command_timeout)
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.last_response_streamed = False

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def run(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        final_text = ""
        self.last_response_streamed = False

        for step in range(1, self.config.max_steps + 1):
            if self.config.stream:
                message, streamed = self._stream_message()
            else:
                streamed = False
                with self.console.spinner("thinking"):
                    message = self.client.chat(self.messages, self.tools.schemas())

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                content = message.get("content") or ""
                self.messages.append({"role": "assistant", "content": content})
                final_text = content
                self.last_response_streamed = streamed and bool(content.strip())
                break

            assistant_message = {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            }
            self.messages.append(assistant_message)

            for call in tool_calls:
                tool_name, raw_arguments, call_id = self._parse_tool_call(call)
                result = self._execute_tool(tool_name, raw_arguments)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": result,
                    }
                )
        else:
            final_text = (
                f"Stopped after {self.config.max_steps} tool/LLM steps. "
                "Ask me to continue if more work is needed."
            )
            self.messages.append({"role": "assistant", "content": final_text})

        return final_text

    def _stream_message(self) -> tuple[dict[str, Any], bool]:
        began = False

        def on_delta(text: str) -> None:
            nonlocal began
            if not began:
                self.console.stream_start()
                began = True
            self.console.stream_delta(text)

        message = self.client.chat_stream(self.messages, self.tools.schemas(), on_delta=on_delta)
        if began:
            self.console.stream_end()
        return message, began

    def _parse_tool_call(self, call: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        function = call.get("function") or {}
        name = function.get("name") or ""
        call_id = call.get("id") or f"call_{len(self.messages)}"
        raw = function.get("arguments") or "{}"
        try:
            arguments = json.loads(raw)
        except json.JSONDecodeError:
            arguments = {}
        return name, arguments, call_id

    def _execute_tool(self, name: str, arguments: dict[str, Any]) -> str:
        try:
            tool = self.tools.get(name)
            summary = self.tools.summarize_args(name, arguments)
            self.console.tool_start(name, summary)
            if tool.requires_approval and not self.config.auto_approve:
                preview = self.tools.preview(name, arguments)
                if preview:
                    self.console.tool_preview(preview)
                if not self.console.confirm(f"Run {name} {summary!r}?"):
                    self.console.tool_done(False, "denied by user")
                    return "Tool call denied by user."
            output = self.tools.execute(name, arguments)
            first_line = output.splitlines()[0] if output.strip() else "completed"
            self.console.tool_done(True, first_line[:160])
            return output
        except (ToolError, LLMError) as exc:
            self.console.tool_done(False, str(exc))
            return f"Tool error: {exc}"
