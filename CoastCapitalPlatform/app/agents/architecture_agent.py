"""
ArchitectureAgent — Daily codebase quality auditor.

Uses Anthropic Claude with tool-use to inspect the CoastCapital codebase,
identify standards violations, and return structured findings.

Checks:
  - Loose coupling / tight cohesion
  - Logging infrastructure consistency
  - Documentation completeness
  - Test coverage gaps
  - Hardcoded values / security issues
  - Docker-compose consistency
"""

import glob
import json
import logging
import os
import subprocess
from typing import Any

import anthropic

from app.config import Config

logger = logging.getLogger(__name__)

# ── Module Registry ───────────────────────────────────────────────────────────

MODULES = [
    {"name": "Finance",           "path": "CoastCapitalFinance",           "has_tests": True},
    {"name": "HomeLab",           "path": "CoastCapitalHomelab",           "has_tests": True},
    {"name": "PersonalAssistant", "path": "CoastCapitalPersonalAssistant", "has_tests": True},
    {"name": "Sports",            "path": "CoastCapitalSports",            "has_tests": True},
    {"name": "Database",          "path": "CoastCapitalDatabase",          "has_tests": True},
    {"name": "N8N",               "path": "CoastCapitalN8N",              "has_tests": False},
    {"name": "Platform",          "path": "CoastCapitalPlatform",          "has_tests": True},
]

# ── Tool Definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "list_files",
        "description": "List files matching a glob pattern within the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g., 'CoastCapitalFinance/app/**/*.py')"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file. Returns up to 500 lines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from workspace root"},
                "max_lines": {"type": "integer", "description": "Max lines to read (default 500)", "default": 500},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a regex pattern across files. Returns matching lines with file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "file_glob": {"type": "string", "description": "Glob to filter files (e.g., '**/*.py')"},
                "max_results": {"type": "integer", "description": "Max results (default 50)", "default": 50},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "check_module_structure",
        "description": "Verify a module has required files: Dockerfile, docker-compose.yml, README.md, tests/, logging_config.",
        "input_schema": {
            "type": "object",
            "properties": {
                "module_path": {"type": "string", "description": "Module directory name (e.g., 'CoastCapitalFinance')"},
            },
            "required": ["module_path"],
        },
    },
    {
        "name": "create_finding",
        "description": "Record an audit finding. Call this for each issue discovered.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["critical", "warning", "info"], "description": "Issue severity"},
                "module": {"type": "string", "description": "Affected module name"},
                "file": {"type": "string", "description": "Affected file path (relative)"},
                "title": {"type": "string", "description": "Short title of the issue"},
                "description": {"type": "string", "description": "Detailed description of the problem"},
                "suggested_fix": {"type": "string", "description": "Concrete suggestion for fixing the issue"},
            },
            "required": ["severity", "module", "title", "description"],
        },
    },
]


# ── Tool Implementations ─────────────────────────────────────────────────────

def _exec_tool(name: str, inputs: dict[str, Any], workspace: str, findings: list) -> str:
    """Execute a tool and return its result as a string."""
    if name == "list_files":
        pattern = os.path.join(workspace, inputs["pattern"])
        matches = sorted(glob.glob(pattern, recursive=True))[:100]
        # Return relative paths
        rel = [os.path.relpath(m, workspace) for m in matches]
        return json.dumps(rel, indent=2)

    elif name == "read_file":
        fpath = os.path.join(workspace, inputs["path"])
        max_lines = inputs.get("max_lines", 500)
        if not os.path.isfile(fpath):
            return f"Error: file not found: {inputs['path']}"
        try:
            with open(fpath, "r", errors="replace") as f:
                lines = f.readlines()[:max_lines]
            return "".join(lines)
        except Exception as exc:
            return f"Error reading file: {exc}"

    elif name == "search_code":
        pattern = inputs["pattern"]
        file_glob = inputs.get("file_glob", "**/*.py")
        max_results = inputs.get("max_results", 50)
        try:
            result = subprocess.run(
                ["grep", "-rn", "-E", pattern, "--include", file_glob, "."],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
            lines = result.stdout.strip().split("\n")[:max_results]
            return "\n".join(lines) if lines[0] else "No matches found."
        except Exception as exc:
            return f"Search error: {exc}"

    elif name == "check_module_structure":
        mod_path = os.path.join(workspace, inputs["module_path"])
        checks = {
            "Dockerfile": os.path.isfile(os.path.join(mod_path, "Dockerfile")),
            "docker-compose.yml": os.path.isfile(os.path.join(mod_path, "docker-compose.yml")),
            "README.md": os.path.isfile(os.path.join(mod_path, "README.md")),
            "tests/": os.path.isdir(os.path.join(mod_path, "tests")),
        }
        # Check for logging_config
        has_logging = bool(glob.glob(os.path.join(mod_path, "**/*logging_config*"), recursive=True))
        checks["logging_config"] = has_logging
        return json.dumps(checks, indent=2)

    elif name == "create_finding":
        finding = {
            "severity": inputs["severity"],
            "module": inputs["module"],
            "file": inputs.get("file", ""),
            "title": inputs["title"],
            "description": inputs["description"],
            "suggested_fix": inputs.get("suggested_fix", ""),
        }
        findings.append(finding)
        return f"Finding recorded: [{finding['severity']}] {finding['title']}"

    return f"Unknown tool: {name}"


# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the ArchitectureAgent for CoastCapital, a multi-module platform with centralized infrastructure.

Your job is to audit the codebase for quality, consistency, and best practices. You run once daily and should ONLY report genuine issues — do not create noise.

## Platform Architecture
- 7 modules: Finance, HomeLab, PersonalAssistant, Sports, Database, N8N, Platform
- Centralized .env at project root (no module-level .env files)
- MySQL 8.4 with medallion pattern (silver/internal/gold per domain)
- Docker containers on shared network, N8N orchestration
- Agent files in /agents/ directory

## Standards to Check

### 1. Loose Coupling
- Modules must NOT import from each other directly
- Communication only via HTTP/REST between containers
- Shared brand assets are mounted read-only, not imported

### 2. Tight Cohesion
- Each module should handle its own domain completely
- Database connections should use env vars, not hardcoded credentials
- Config should be centralized per module (one config.py or config class)

### 3. Logging
- All modules should use structured JSON logging (logging_config.py)
- LOG_DIR should be configurable via environment variable
- No print() statements in production code

### 4. Documentation
- Every module needs README.md
- Agent definitions in /agents/ should match implementations

### 5. Security
- No hardcoded passwords, API keys, or secrets
- Database users should use env vars (MYSQL_USER/MYSQL_PASSWORD)
- No root database access

### 6. Testing
- Every module should have tests/ directory
- Test conftest.py should mock external dependencies

### 7. Docker
- All modules should have source volume mounts for dev
- Healthchecks should be in docker-compose.yml (not Dockerfile)

## Audit Process
1. Check each module's structure using check_module_structure
2. Read key files (config.py, main.py, docker-compose.yml) for pattern violations
3. Search for anti-patterns (hardcoded values, print statements, cross-module imports)
4. Record ONLY genuine issues using create_finding
5. Be precise — include file paths and line context in descriptions

If the codebase is clean, return zero findings. Do NOT invent issues.
"""


# ── Main Audit Function ──────────────────────────────────────────────────────

async def run_audit(
    workspace_root: str,
    modules: list[str] | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Run the architecture audit using Claude with tool-use.

    Args:
        workspace_root: Path to the CoastCapital repo root.
        modules: Optional list of module names to audit (None = all).
        dry_run: If True, skip the actual Claude call and return empty.

    Returns:
        List of finding dicts with severity, module, file, title, description, suggested_fix.
    """
    if dry_run:
        logger.info("Dry run — skipping audit")
        return []

    if not Config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set — cannot run audit")
        return [{"severity": "critical", "module": "Platform", "title": "Missing API key",
                 "description": "ANTHROPIC_API_KEY is not configured. Cannot run architecture audit.",
                 "file": "", "suggested_fix": "Set ANTHROPIC_API_KEY in .env"}]

    # Filter modules if specified
    target_modules = MODULES
    if modules:
        target_modules = [m for m in MODULES if m["name"].lower() in [x.lower() for x in modules]]

    module_summary = ", ".join(m["name"] for m in target_modules)
    user_msg = f"Audit the following modules: {module_summary}. Check structure, standards, security, and documentation. Only report genuine issues."

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    findings: list[dict[str, Any]] = []
    messages = [{"role": "user", "content": user_msg}]

    # Agentic loop — let Claude use tools until it's done
    max_turns = 20
    for turn in range(max_turns):
        response = client.messages.create(
            model=Config.CLAUDE_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Collect assistant text and tool-use blocks
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        # Check if Claude is done (no more tool calls)
        tool_calls = [b for b in assistant_content if b.type == "tool_use"]
        if not tool_calls:
            logger.info("Audit complete after %d turns, %d findings", turn + 1, len(findings))
            break

        # Execute each tool call
        tool_results = []
        for tc in tool_calls:
            result_text = _exec_tool(tc.name, tc.input, workspace_root, findings)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result_text,
            })

        messages.append({"role": "user", "content": tool_results})

    return findings
