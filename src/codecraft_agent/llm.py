from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMError(RuntimeError):
    """Raised when the LLM provider returns an error or malformed response."""


class OpenAICompatibleClient:
    """Small raw HTTP client for OpenAI-compatible chat-completions APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.2,
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> dict[str, Any]:
        if not self.api_key:
            raise LLMError(
                "missing API key. Set the provider API key environment variable, "
                "CODECRAFT_API_KEY, or pass --api-key."
            )

        payload = self._payload(messages, tools, tool_choice=tool_choice)
        body = self._post(payload)

        try:
            parsed = json.loads(body)
            return parsed["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError(f"provider returned an unexpected response: {body[:1000]}") from exc

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        on_delta: Callable[[str], None] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> dict[str, Any]:
        if not self.api_key:
            raise LLMError(
                "missing API key. Set the provider API key environment variable, "
                "CODECRAFT_API_KEY, or pass --api-key."
            )

        payload = self._payload(messages, tools, stream=True, tool_choice=tool_choice)
        request = self._request(payload)
        content_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        role = "assistant"

        try:
            with urlopen(request, timeout=self.timeout) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta") or {}
                    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                        raise LLMError(f"provider returned an invalid stream chunk: {data}") from exc

                    if delta.get("role"):
                        role = delta["role"]
                    piece = delta.get("content")
                    if piece:
                        content_parts.append(piece)
                        if on_delta:
                            on_delta(piece)
                    for tool_delta in delta.get("tool_calls") or []:
                        self._merge_tool_delta(tool_calls, tool_delta)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"provider returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise LLMError(f"could not reach provider: {exc.reason}") from exc

        message: dict[str, Any] = {"role": role, "content": "".join(content_parts)}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message

    def _payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        stream: bool = False,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if stream:
            payload["stream"] = True
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        return payload

    def _request(self, payload: dict[str, Any]) -> Request:
        return Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream" if payload.get("stream") else "application/json",
            },
            method="POST",
        )

    def _post(self, payload: dict[str, Any]) -> str:
        request = self._request(payload)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"provider returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise LLMError(f"could not reach provider: {exc.reason}") from exc

    def _merge_tool_delta(self, tool_calls: list[dict[str, Any]], delta: dict[str, Any]) -> None:
        index = int(delta.get("index", len(tool_calls)))
        while len(tool_calls) <= index:
            tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})

        target = tool_calls[index]
        if delta.get("id"):
            target["id"] = delta["id"]
        if delta.get("type"):
            target["type"] = delta["type"]

        function_delta = delta.get("function") or {}
        function = target.setdefault("function", {"name": "", "arguments": ""})
        if function_delta.get("name"):
            function["name"] = function.get("name", "") + function_delta["name"]
        if function_delta.get("arguments"):
            function["arguments"] = function.get("arguments", "") + function_delta["arguments"]
