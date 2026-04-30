from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class AgentConfig:
    workspace: Path
    model: str
    base_url: str
    api_key: str
    temperature: float = 0.2
    max_steps: int = 12
    command_timeout: int = 30
    auto_approve: bool = False
    color: bool = True


def load_config(
    *,
    workspace: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_key_env: str = "OPENAI_API_KEY",
    temperature: float = 0.2,
    max_steps: int = 12,
    command_timeout: int = 30,
    auto_approve: bool = False,
    color: bool = True,
) -> AgentConfig:
    resolved_workspace = Path(workspace or os.getcwd()).expanduser().resolve()
    resolved_model = model or os.getenv("CODECRAFT_MODEL") or DEFAULT_MODEL
    resolved_base = (base_url or os.getenv("CODECRAFT_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    resolved_key = api_key or os.getenv(api_key_env) or os.getenv("CODECRAFT_API_KEY") or ""

    return AgentConfig(
        workspace=resolved_workspace,
        model=resolved_model,
        base_url=resolved_base,
        api_key=resolved_key,
        temperature=temperature,
        max_steps=max_steps,
        command_timeout=command_timeout,
        auto_approve=auto_approve,
        color=color,
    )

