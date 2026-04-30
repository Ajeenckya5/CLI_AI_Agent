from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .agent import Agent
from .config import (
    DEFAULT_API_KEY_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    PROVIDER_DEFAULTS,
    load_config,
)
from .llm import LLMError
from .ui import Console


HELP_TEXT = """Commands:
  /help        Show this help
  /clear       Clear conversation context
  /cwd         Show active workspace
  /tools       List available local tools
  /exit        Quit

Tips:
  Ask for concrete work, for example:
    "Inspect this project and add unit tests for the parser"
    "Build a small CLI that summarizes CSV files"
    "Find the bug in the failing tests and fix it"
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codecraft",
        description="CLI coding agent using raw xAI/OpenAI-compatible LLM API calls.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--workspace", default=os.getcwd(), help="Workspace directory. Defaults to cwd.")
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDER_DEFAULTS),
        default=None,
        help=f"Provider defaults to use. Default: env CODECRAFT_PROVIDER or {DEFAULT_PROVIDER}.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Model name. Default for {DEFAULT_PROVIDER}: {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=f"API base URL. Default for {DEFAULT_PROVIDER}: {DEFAULT_BASE_URL}.",
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help=f"Environment variable containing the API key. Default for {DEFAULT_PROVIDER}: {DEFAULT_API_KEY_ENV}.",
    )
    parser.add_argument("--api-key", default=None, help="API key value. Prefer an environment variable.")
    parser.add_argument("--temperature", type=float, default=0.2, help="LLM temperature.")
    parser.add_argument("--max-steps", type=int, default=12, help="Maximum LLM/tool loop steps per request.")
    parser.add_argument("--command-timeout", type=int, default=30, help="Default shell command timeout in seconds.")
    parser.add_argument(
        "-y",
        "--auto-approve",
        action="store_true",
        help="Allow write and shell tools without interactive confirmation.",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    parser.add_argument("--once", help="Run one prompt and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(
            workspace=args.workspace,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            api_key_env=args.api_key_env,
            temperature=args.temperature,
            max_steps=args.max_steps,
            command_timeout=args.command_timeout,
            auto_approve=args.auto_approve,
            color=not args.no_color,
        )
    except ValueError as exc:
        console = Console(color=not args.no_color)
        console.error(str(exc))
        return 2
    console = Console(color=config.color)

    if not config.api_key:
        console.error(
            f"missing API key. Set {config.api_key_env}, CODECRAFT_API_KEY, or pass --api-key."
        )
        console.system(f"Example: export {config.api_key_env}='...' && codecraft --workspace .")
        return 2

    agent = Agent(config, console)

    if args.once:
        try:
            console.assistant(agent.run(args.once))
            return 0
        except LLMError as exc:
            console.error(str(exc))
            return 1

    console.banner(config.provider, config.model, str(config.workspace))
    while True:
        try:
            user_text = input(console.prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not user_text:
            continue
        if user_text.startswith("/"):
            if user_text in {"/exit", "/quit"}:
                return 0
            if user_text == "/help":
                console.system(HELP_TEXT)
                continue
            if user_text == "/clear":
                agent.reset()
                console.system("conversation context cleared")
                continue
            if user_text == "/cwd":
                console.system(str(config.workspace))
                continue
            if user_text == "/tools":
                for tool in agent.tools.tools:
                    flag = "approval" if tool.requires_approval else "read-only"
                    console.system(f"{tool.name:16} {flag:9} {tool.description}")
                continue
            console.warn(f"unknown command: {user_text}")
            continue

        try:
            console.assistant(agent.run(user_text))
        except LLMError as exc:
            console.error(str(exc))
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
