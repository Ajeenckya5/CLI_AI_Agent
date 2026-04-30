from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_PROVIDER = "xai"
PROVIDER_DEFAULTS = {
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "model": "grok-4.20-reasoning",
        "api_key_env": "XAI_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
    },
}
DEFAULT_BASE_URL = PROVIDER_DEFAULTS[DEFAULT_PROVIDER]["base_url"]
DEFAULT_MODEL = PROVIDER_DEFAULTS[DEFAULT_PROVIDER]["model"]
DEFAULT_API_KEY_ENV = PROVIDER_DEFAULTS[DEFAULT_PROVIDER]["api_key_env"]


@dataclass(frozen=True)
class AgentConfig:
    workspace: Path
    provider: str
    model: str
    base_url: str
    api_key: str
    api_key_env: str
    temperature: float = 0.2
    max_steps: int = 12
    command_timeout: int = 30
    auto_approve: bool = False
    color: bool = True


def load_config(
    *,
    workspace: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    temperature: float = 0.2,
    max_steps: int = 12,
    command_timeout: int = 30,
    auto_approve: bool = False,
    color: bool = True,
) -> AgentConfig:
    resolved_workspace = Path(workspace or os.getcwd()).expanduser().resolve()
    resolved_provider = (provider or os.getenv("CODECRAFT_PROVIDER") or DEFAULT_PROVIDER).lower()
    if resolved_provider not in PROVIDER_DEFAULTS:
        valid = ", ".join(sorted(PROVIDER_DEFAULTS))
        raise ValueError(f"unknown provider {resolved_provider!r}; expected one of: {valid}")

    defaults = PROVIDER_DEFAULTS[resolved_provider]
    resolved_key_env = api_key_env or defaults["api_key_env"]
    resolved_model = model or os.getenv("CODECRAFT_MODEL") or defaults["model"]
    resolved_base = (base_url or os.getenv("CODECRAFT_BASE_URL") or defaults["base_url"]).rstrip("/")
    resolved_key = api_key or os.getenv(resolved_key_env) or os.getenv("CODECRAFT_API_KEY") or ""

    return AgentConfig(
        workspace=resolved_workspace,
        provider=resolved_provider,
        model=resolved_model,
        base_url=resolved_base,
        api_key=resolved_key,
        api_key_env=resolved_key_env,
        temperature=temperature,
        max_steps=max_steps,
        command_timeout=command_timeout,
        auto_approve=auto_approve,
        color=color,
    )
