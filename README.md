# CodeCraft Agent

CodeCraft Agent is a professional command-line coding agent built with raw LLM
API calls. It accepts programming requests in a terminal, sends them to the xAI
OpenAI-compatible chat-completions API, executes model-requested tool calls, and
returns readable progress and results.

It does not use LangChain, Strands, CrewAI, AutoGen, or any similar agentic
framework. The only runtime dependency is Python.

## Features

- Interactive CLI with clear prompts, status messages, and tool feedback.
- Streaming assistant output by default.
- Raw HTTPS calls to xAI's `/v1/chat/completions` endpoint using Python standard library only.
- xAI defaults with OpenAI-compatible provider support through `--provider`, `--base-url`, and `--model`.
- Native function/tool calling loop.
- Diff previews before approved file writes and replacements.
- `doctor` command for API/model/tool-call diagnostics.
- `context` command for project detection and suggested test commands.
- Workspace-scoped local tools:
  - `project_context`
  - `list_files`
  - `read_file`
  - `search_files`
  - `write_file`
  - `replace_in_file`
  - `make_directory`
  - `git_status`
  - `git_diff`
  - `run_tests`
  - `run_command`
- Approval prompts for file writes and shell commands by default.
- `--auto-approve` mode for trusted local automation.
- Unit tests for tool execution and the LLM/tool loop.
- Included example project built as an agent deliverable: `examples/built_by_agent/logscope`.

## Project Layout

```text
codecraft-agent/
  src/codecraft_agent/
    agent.py      # conversation loop and tool-call execution
    cli.py        # terminal interface
    config.py     # environment and CLI configuration
    context.py    # workspace/project inspection
    doctor.py     # provider diagnostics
    llm.py        # raw xAI/OpenAI-compatible HTTP client
    tools.py      # local coding tools
    ui.py         # terminal formatting and prompts
  tests/
  examples/built_by_agent/logscope/
  README.md
  pyproject.toml
```

## Installation

From this folder:

```bash
cd /Users/aj/Downloads/codecraft-agent
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Confirm the CLI is installed:

```bash
codecraft --help
```

## Configuration

CodeCraft uses xAI by default:

```text
provider: xai
base URL: https://api.x.ai/v1
model: grok-4.20-reasoning
key env: XAI_API_KEY
```

### xAI

```bash
export XAI_API_KEY="your-xai-api-key"
codecraft --workspace /path/to/project
```

The default xAI model is `grok-4.20-reasoning`. You can override it:

```bash
codecraft --model grok-4 --workspace /path/to/project
```

### OpenAI

OpenAI is still available through provider defaults:

```bash
export OPENAI_API_KEY="your-openai-api-key"
codecraft --provider openai --workspace /path/to/project
```

### Other OpenAI-Compatible Providers

Set a compatible base URL and model:

```bash
export CODECRAFT_API_KEY="your-provider-key"
codecraft \
  --base-url "https://provider.example.com/v1" \
  --model "provider-model-name" \
  --workspace /path/to/project
```

Environment variables:

```bash
CODECRAFT_API_KEY     # fallback API key
CODECRAFT_BASE_URL    # fallback base URL
CODECRAFT_MODEL       # fallback model
CODECRAFT_PROVIDER    # xai or openai
XAI_API_KEY           # default xAI key env var
OPENAI_API_KEY        # default OpenAI key env var when --provider openai is used
```

You can also use a different key variable:

```bash
export MY_PROVIDER_KEY="..."
codecraft --api-key-env MY_PROVIDER_KEY
```

## Usage

Start an interactive session:

```bash
codecraft --workspace /path/to/project
```

Run diagnostics against xAI:

```bash
codecraft doctor
```

Inspect a workspace without using the LLM:

```bash
codecraft context --workspace /path/to/project
```

Example prompts:

```text
Inspect this project and explain how it is structured.
Add unit tests for the parser.
Find why the test suite is failing and fix it.
Build a small CLI that summarizes CSV files.
Refactor the cache module to make eviction deterministic.
```

Run a single prompt and exit:

```bash
codecraft --workspace /path/to/project --once "Inspect the repo and suggest the next test to add"
```

Disable streaming output:

```bash
codecraft --no-stream --workspace /path/to/project
```

Allow write and shell tools without confirmation:

```bash
codecraft --workspace /path/to/project --auto-approve
```

Interactive commands:

```text
/help    show CLI help
/clear   clear conversation context
/context show detected project context
/doctor  check provider, model, key, chat, and tool calling
/cwd     show active workspace
/tools   list available local tools
/exit    quit
```

## Safety Model

All file paths are resolved inside the configured workspace. Attempts to read or
write outside that directory are rejected by the tool layer.

By default, these tools require confirmation:

- `write_file`
- `replace_in_file`
- `make_directory`
- `run_tests`
- `run_command`

For file edits, CodeCraft shows a unified diff preview before asking for
approval. For shell commands, it labels command risk and blocks clearly
dangerous commands such as recursive deletion of the filesystem root, `sudo`,
filesystem formatting, and disk erase operations.

Use `--auto-approve` only in a workspace you trust.

## How Tool Calling Works

1. The user enters a programming request.
2. CodeCraft sends the conversation and JSON tool schemas to the configured LLM.
3. If the model returns tool calls, CodeCraft parses the function name and JSON arguments.
4. CodeCraft executes the local tool inside the workspace.
5. Tool results are appended to the conversation as tool messages.
6. The loop continues until the model returns a final answer or `--max-steps` is reached.

The implementation lives in:

- `src/codecraft_agent/llm.py`
- `src/codecraft_agent/agent.py`
- `src/codecraft_agent/tools.py`

## Verification

Run the agent test suite:

```bash
cd /Users/aj/Downloads/codecraft-agent
PYTHONPATH=src python3 -m unittest discover -s tests
```

Run the included example project tests:

```bash
cd /Users/aj/Downloads/codecraft-agent/examples/built_by_agent/logscope
python3 -m unittest discover -s .
```

Try the example program:

```bash
python3 logscope.py sample.log --top 3
```

## Example Project Built by the Agent

`examples/built_by_agent/logscope` contains LogScope, a non-trivial Python CLI
for analyzing logs. It can parse JSONL and plain-text log formats, aggregate by
level/service/status, build minute or hour timelines, detect bursts, and emit
text or JSON reports.

Example:

```bash
cd /Users/aj/Downloads/codecraft-agent/examples/built_by_agent/logscope
python3 logscope.py sample.log --service api --bucket minute
```

## Development Notes

This project intentionally avoids runtime dependencies. If you want richer
terminal rendering later, add a small UI dependency such as `rich`, but the
current implementation is fully functional with the Python standard library.
