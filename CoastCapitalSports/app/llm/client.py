"""
client.py — Parameterised LLM client for sports news summarisation.

Reads provider settings from environment variables so the LLM endpoint
can be swapped without code changes (Anthropic, OpenAI, or custom MCP).

Usage::

    from llm.client import LLMClient
    client = LLMClient()
    summary = client.summarize("Article text here …")
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported provider implementations
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a sports analyst for Coast Capital. "
    "Summarize the following sports news in 2-3 concise sentences. "
    "Focus on key outcomes, player impacts, and implications for upcoming games."
)


class LLMClient:
    """Configurable LLM client that reads provider settings from environment.

    Environment variables
    ---------------------
    LLM_PROVIDER  : ``"anthropic"`` | ``"openai"`` | ``"mcp"``  (default ``"anthropic"``)
    LLM_API_KEY   : API key for the provider.
    LLM_MODEL     : Model identifier (e.g. ``"claude-sonnet-4-20250514"``).
    LLM_BASE_URL  : Base URL for the API (e.g. ``"https://api.anthropic.com"``).
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
        self.api_key = os.getenv("LLM_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.anthropic.com").rstrip("/")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def summarize(self, text: str, context: str = "") -> str:
        """Send *text* to the configured LLM and return a concise summary.

        Parameters
        ----------
        text    : The article body / description to summarise.
        context : Optional extra context (e.g. ``"Focus on the Indianapolis Colts"``).

        Returns
        -------
        str — The summary text, or a placeholder if the LLM is unreachable.
        """
        if not self.api_key:
            return "(LLM summary unavailable — set LLM_API_KEY in .env)"

        user_message = text
        if context:
            user_message = f"{context}\n\n{text}"

        try:
            if self.provider == "anthropic":
                return self._call_anthropic(user_message)
            elif self.provider == "openai":
                return self._call_openai(user_message)
            else:
                # Generic MCP / custom endpoint
                return self._call_mcp(user_message)
        except Exception as exc:
            logger.error("LLMClient.summarize failed (%s): %s", self.provider, exc)
            return "(LLM summary unavailable — API error)"

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _call_anthropic(self, user_message: str) -> str:
        """Call the Anthropic Messages API."""
        url = f"{self.base_url}/v1/messages"
        resp = requests.post(
            url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 300,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json().get("content", [])
        return content[0].get("text", "") if content else ""

    def _call_openai(self, user_message: str) -> str:
        """Call an OpenAI-compatible chat completions endpoint."""
        url = f"{self.base_url}/v1/chat/completions"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 300,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        choices = resp.json().get("choices", [])
        return choices[0]["message"]["content"] if choices else ""

    def _call_mcp(self, user_message: str) -> str:
        """Call a generic MCP-compatible endpoint.

        Expects the endpoint at ``{base_url}/v1/messages`` to accept the
        same payload shape as the Anthropic Messages API.
        """
        url = f"{self.base_url}/v1/messages"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 300,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # Try Anthropic shape first, then OpenAI shape
        content = data.get("content", [])
        if content:
            return content[0].get("text", "")
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""
