"""
MCP (Model Context Protocol) server for CoastCapital intent classification.

Exposes the Ollama-powered dispatcher as an MCP tool that Claude Code can use.
Run via: python mcp_server.py (stdio transport)

Register in .claude/settings.local.json:
  "mcpServers": {
    "coastcapital-dispatcher": {
      "command": "python3",
      "args": ["CoastCapitalPlatform/mcp_server.py"],
      "env": { "OLLAMA_BASE_URL": "http://localhost:11434" }
    }
  }
"""

import asyncio
import json
import sys
import os

# Ensure app package is importable
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from app.dispatcher import classify_intent, get_intent_registry, IntentResult

server = Server("coastcapital-dispatcher")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="classify_intent",
            description=(
                "Classify a natural-language message into a CoastCapital N8N workflow intent. "
                "Returns the intent ID, parameters, confidence score, and webhook path. "
                "Uses local Ollama for classification."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The user message to classify (e.g., 'run the daily sports pipeline for NFL')",
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="list_intents",
            description="List all available N8N workflow intents with their webhook paths and parameters.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "classify_intent":
        text = arguments.get("text", "")
        result = classify_intent(text)
        return [TextContent(type="text", text=json.dumps(result.to_dict(), indent=2))]

    elif name == "list_intents":
        intents = get_intent_registry()
        return [TextContent(type="text", text=json.dumps(intents, indent=2))]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
