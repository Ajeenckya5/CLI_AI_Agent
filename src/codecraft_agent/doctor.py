from __future__ import annotations

import json
import platform

from .config import AgentConfig
from .llm import LLMError, OpenAICompatibleClient
from .ui import Console


def run_doctor(config: AgentConfig, console: Console) -> int:
    console.system("CodeCraft doctor")
    console.system(f"provider: {config.provider}")
    console.system(f"base_url: {config.base_url}")
    console.system(f"model: {config.model}")
    console.system(f"workspace: {config.workspace}")
    console.system(f"python: {platform.python_version()}")
    console.system(f"api key env: {config.api_key_env} ({'present' if config.api_key else 'missing'})")

    if not config.workspace.exists():
        console.error("workspace does not exist")
        return 2
    if not config.api_key:
        console.error(f"missing API key. Set {config.api_key_env}, CODECRAFT_API_KEY, or pass --api-key.")
        return 2

    client = OpenAICompatibleClient(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=0,
        timeout=60,
    )

    try:
        message = client.chat(
            [
                {"role": "system", "content": "You are a terse diagnostic assistant."},
                {"role": "user", "content": "Reply with exactly: OK"},
            ],
            [],
        )
    except LLMError as exc:
        console.error(f"chat completion failed: {exc}")
        return 1

    console.system("chat completion: ok")
    content = (message.get("content") or "").strip()
    if content:
        console.system(f"model response: {content[:120]}")

    tool_schema = [
        {
            "type": "function",
            "function": {
                "name": "doctor_echo",
                "description": "Echo a diagnostic value.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            },
        }
    ]
    try:
        tool_message = client.chat(
            [
                {
                    "role": "system",
                    "content": "You are testing tool calling. Use the provided function when requested.",
                },
                {
                    "role": "user",
                    "content": "Call doctor_echo with value set to ok. Do not answer directly.",
                },
            ],
            tool_schema,
            tool_choice={"type": "function", "function": {"name": "doctor_echo"}},
        )
    except LLMError as exc:
        console.error(f"tool-call check failed: {exc}")
        return 1

    tool_calls = tool_message.get("tool_calls") or []
    if not tool_calls:
        console.warn("tool-call check did not produce a tool call")
        return 1

    call = tool_calls[0]
    function = call.get("function") or {}
    name = function.get("name")
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError:
        arguments = {}

    if name != "doctor_echo" or arguments.get("value") != "ok":
        console.warn("tool-call check returned an unexpected tool call")
        return 1

    console.system("tool calling: ok")
    return 0
