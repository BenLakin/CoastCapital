"""
Ollama-powered intent classifier for CoastCapital N8N workflow dispatch.

Takes natural-language text (e.g. from Slack) and returns a structured
intent with parameters and confidence score.  Calls the local Ollama
server -- no external API keys required.

Ground truth feedback (upvotes/downvotes from the dashboard) is included
in the system prompt to improve classification accuracy over time.
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any

import requests

from app.config import Config

logger = logging.getLogger(__name__)

# -- Intent Registry -----------------------------------------------------------

INTENTS: list[dict[str, Any]] = [
    # Finance
    {"id": "finance_forecast",   "webhook": "/webhook/finance-forecast",    "params": ["tickers"],                     "desc": "Run daily stock forecast"},
    {"id": "finance_retrain",    "webhook": "/webhook/finance-retrain",     "params": [],                              "desc": "Retrain finance ML models"},
    {"id": "finance_watchlist",  "webhook": "/webhook/finance-watchlist",   "params": ["add_tickers", "remove_tickers"], "desc": "Sync stock watchlist"},
    # HomeLab
    {"id": "homelab_health",     "webhook": "/webhook/homelab-health",      "params": ["service"],                     "desc": "Check homelab service health"},
    {"id": "homelab_report",     "webhook": "/webhook/homelab-report",      "params": [],                              "desc": "Generate daily homelab report"},
    {"id": "homelab_full_status","webhook": "/webhook/homelab-full-status", "params": [],                              "desc": "Full status sweep of all homelab services"},
    # Assistant
    {"id": "assistant_brief",    "webhook": "/webhook/assistant-brief",     "params": [],                              "desc": "Morning briefing (email, calendar, news)"},
    {"id": "assistant_tasks",    "webhook": "/webhook/assistant-tasks",     "params": [],                              "desc": "Sync tasks from Todoist/Notion"},
    {"id": "assistant_followup", "webhook": "/webhook/assistant-followup",  "params": [],                              "desc": "Check for unanswered emails"},
    # Sports
    {"id": "sports_daily",       "webhook": "/webhook/sports-daily",        "params": ["sport"],                       "desc": "Daily sports data pipeline"},
    {"id": "sports_nfl_picks",   "webhook": "/webhook/sports-nfl-picks",    "params": ["week"],                        "desc": "NFL weekly betting picks"},
    {"id": "sports_nfl_ingest",  "webhook": "/webhook/sports-nfl-ingest",   "params": [],                              "desc": "Ingest latest NFL game data"},
    {"id": "sports_ncaa_bracket","webhook": "/webhook/sports-ncaa-bracket", "params": ["season", "n_simulations"],     "desc": "Simulate NCAA tournament bracket"},
    {"id": "sports_ncaa_prep",   "webhook": "/webhook/sports-ncaa-prep",    "params": [],                              "desc": "Full NCAA tournament prep pipeline (backfill+train+simulate)"},
    {"id": "sports_backfill",    "webhook": "/webhook/sports-backfill",     "params": ["sport", "start_date", "end_date"], "desc": "Backfill historical sports data"},
    {"id": "sports_news",        "webhook": "/webhook/sports-news",         "params": ["sport"],                       "desc": "Ingest sports news articles"},
    {"id": "sports_optimization","webhook": "/webhook/sports-optimization", "params": ["sport"],                       "desc": "Weekly model optimization and betting strategy"},
    # Database
    {"id": "db_maintenance",     "webhook": "/webhook/db-maintenance",      "params": ["job_type", "schema_name"],     "desc": "Run MySQL maintenance (optimize, analyze, health check)"},
    # Platform
    {"id": "system_status",      "webhook": "/webhook/platform-system-status", "params": [],                           "desc": "Platform-wide system status check"},
    {"id": "docker_rebuild",     "webhook": "/webhook/docker-rebuild",      "params": ["modules"],                     "desc": "Rebuild Docker containers (skip MySQL+N8N)"},
    {"id": "architecture_audit", "webhook": "/webhook/platform-architecture-audit", "params": [],                      "desc": "Run code quality and architecture audit"},
]


def _build_ground_truth_section() -> str:
    """Build few-shot examples from upvoted/downvoted predictions in the DB.

    Returns a string to append to the system prompt, or empty string if
    no feedback is available or the DB is unreachable.
    """
    try:
        from app.db import get_good_examples, get_bad_examples

        good = get_good_examples(limit=Config.MAX_GOOD_EXAMPLES)
        bad = get_bad_examples(limit=Config.MAX_BAD_EXAMPLES)

        if not good and not bad:
            return ""

        lines = ["\n\nHere are examples from previous classifications with user feedback:"]

        if good:
            lines.append("\nCORRECT classifications (user confirmed these were right):")
            for ex in good:
                params = ex.get("predicted_params") or "{}"
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except json.JSONDecodeError:
                        params = {}
                # Truncate and sanitize user text to prevent prompt injection
                safe_text = ex["user_text"][:120].replace('"', "'")
                lines.append(
                    f'  Input: "{safe_text}" -> '
                    f'{{"intent": "{ex["predicted_intent"]}", "params": {json.dumps(params)}}}'
                )

        if bad:
            lines.append("\nINCORRECT classifications (user said these were wrong):")
            for ex in bad:
                correct = ex.get("correct_intent") or "unknown"
                note = ex.get("feedback_note") or ""
                safe_text = ex["user_text"][:120].replace('"', "'")
                line = (
                    f'  Input: "{safe_text}" -> '
                    f'predicted "{ex["predicted_intent"]}" but correct was "{correct}"'
                )
                if note:
                    line += f" (note: {note})"
                lines.append(line)

        lines.append("\nUse these examples to improve your classification accuracy.")
        return "\n".join(lines)

    except Exception as exc:
        logger.debug("Could not load ground truth (DB may be unavailable): %s", exc)
        return ""


def _build_system_prompt() -> str:
    """Build the system prompt with all available intents + ground truth examples."""
    intent_lines = []
    for i in INTENTS:
        params_str = ", ".join(i["params"]) if i["params"] else "none"
        intent_lines.append(f'- {i["id"]} (params: {params_str}) -- {i["desc"]}')

    ground_truth = _build_ground_truth_section()

    return f"""You are a job dispatcher for CoastCapital, a multi-module platform.
Given a user message, classify the intent and extract any relevant parameters.

Available intents:
{chr(10).join(intent_lines)}
- unclear -- use when the request is ambiguous or doesn't match any intent

Rules:
1. Pick the SINGLE best matching intent.
2. Extract parameters from the message when mentioned.
3. Set confidence 0.0-1.0 based on how certain you are.
4. If unclear, set intent to "unclear" and provide a clarification question.
5. Respond with ONLY valid JSON -- no other text.

JSON format:
{{"intent": "<id>", "params": {{}}, "confidence": 0.85, "clarification": null}}
{ground_truth}"""


@dataclass
class IntentResult:
    """Structured result from intent classification."""

    intent: str = "unclear"
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    clarification: str | None = None
    webhook_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_intent(text: str) -> IntentResult:
    """Classify user text into an N8N workflow intent using local Ollama.

    Returns an IntentResult with intent ID, extracted parameters,
    confidence score, and the webhook path to dispatch to.
    """
    system_prompt = _build_system_prompt()
    user_prompt = f"User message: {text}"

    try:
        resp = requests.post(
            f"{Config.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": Config.OLLAMA_MODEL,
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
                "format": "json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
    except requests.RequestException as exc:
        logger.error("Ollama request failed: %s", exc)
        return IntentResult(
            intent="unclear",
            confidence=0.0,
            clarification="Sorry, I couldn't process that -- the LLM service is unavailable.",
        )

    # Parse JSON from Ollama response
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Could not parse Ollama response: %s", raw[:200])
                return IntentResult(
                    intent="unclear",
                    confidence=0.0,
                    clarification="I couldn't understand the classification. Could you rephrase?",
                )
        else:
            logger.warning("No JSON found in Ollama response: %s", raw[:200])
            return IntentResult(
                intent="unclear",
                confidence=0.0,
                clarification="I couldn't understand the classification. Could you rephrase?",
            )

    # Build result
    intent_id = parsed.get("intent", "unclear")
    confidence = float(parsed.get("confidence", 0.0))
    params = parsed.get("params") or {}
    clarification = parsed.get("clarification")

    # Look up webhook path
    webhook_path = None
    for i in INTENTS:
        if i["id"] == intent_id:
            webhook_path = i["webhook"]
            break

    # Force clarification for low confidence
    if confidence < 0.6 and intent_id != "unclear":
        intent_id = "unclear"
        clarification = clarification or f"I'm {confidence:.0%} sure you want '{intent_id}'. Can you confirm?"

    return IntentResult(
        intent=intent_id,
        params=params,
        confidence=confidence,
        clarification=clarification,
        webhook_path=webhook_path,
    )


def get_intent_registry() -> list[dict[str, Any]]:
    """Return the full intent registry for documentation/tooling."""
    return INTENTS
