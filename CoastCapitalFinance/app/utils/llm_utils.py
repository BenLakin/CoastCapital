"""
LLM utilities — parameterized provider support.

Providers:
  - gemini   : Google Gemini via REST API (primary for stocks of interest)
  - ollama   : Local Ollama instance (secondary for big movers)
  - anthropic: Anthropic Claude (fallback / legacy)

Usage:
  - Stocks of interest (watchlist) use LLM_PROVIDER_PRIMARY (default: gemini)
  - Other stocks (big movers) use LLM_PROVIDER_SECONDARY (default: ollama)
  - Max 3 articles per stock per day are sent for LLM analysis
"""
import json
import requests
from typing import Optional
from datetime import datetime, timezone
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Provider clients (lazy singletons) ────────────────────────────────────

_anthropic_client = None
_gemini_session = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        _anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_gemini_session() -> requests.Session:
    global _gemini_session
    if _gemini_session is None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured")
        _gemini_session = requests.Session()
    return _gemini_session


# ── Unified LLM call ─────────────────────────────────────────────────────

def _call_llm(prompt: str, provider: str = None, max_tokens: int = 1024) -> str:
    """
    Send a prompt to the configured LLM provider. Returns raw text response.

    Args:
        prompt: The prompt text.
        provider: "gemini", "ollama", or "anthropic". Defaults to LLM_PROVIDER_PRIMARY.
        max_tokens: Max response tokens.
    """
    provider = provider or settings.LLM_PROVIDER_PRIMARY

    if provider == "gemini":
        return _call_gemini(prompt, max_tokens)
    elif provider == "ollama":
        return _call_ollama(prompt, max_tokens)
    elif provider == "anthropic":
        return _call_anthropic(prompt, max_tokens)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def _call_gemini(prompt: str, max_tokens: int = 1024) -> str:
    """Call Google Gemini via REST API."""
    session = _get_gemini_session()
    url = (
        f"{settings.GEMINI_BASE_URL}/models/{settings.GEMINI_MODEL}:generateContent"
        f"?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.2,
        },
    }
    resp = session.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    # Extract text from Gemini response
    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Empty Gemini response")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise ValueError("No content in Gemini response")
    return parts[0].get("text", "").strip()


def _call_ollama(prompt: str, max_tokens: int = 1024) -> str:
    """Call local Ollama instance."""
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.2,
        },
    }
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "").strip()


def _call_anthropic(prompt: str, max_tokens: int = 1024) -> str:
    """Call Anthropic Claude."""
    client = _get_anthropic_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _get_model_name(provider: str = None) -> str:
    """Return the model name for a given provider."""
    provider = provider or settings.LLM_PROVIDER_PRIMARY
    if provider == "gemini":
        return settings.GEMINI_MODEL
    elif provider == "ollama":
        return settings.OLLAMA_MODEL
    elif provider == "anthropic":
        return "claude-sonnet-4-6"
    return provider


# ── Public API (backward-compatible) ─────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def analyze_news_article(
    ticker: str,
    company_name: str,
    headline: str,
    article_text: str,
    provider: str = None,
) -> dict:
    """
    Analyze a news article for a stock using the configured LLM provider.
    Returns sentiment, summary, key points, catalysts, and risks.
    """
    prompt = f"""You are an elite Wall Street analyst with deep expertise in equity research.
Analyze this news article about {company_name} ({ticker}) and provide a structured assessment.

HEADLINE: {headline}

ARTICLE TEXT:
{article_text[:4000]}

Provide your analysis in the following JSON format:
{{
  "summary": "2-3 sentence summary of key news",
  "key_points": ["bullet point 1", "bullet point 2", "bullet point 3"],
  "price_catalysts": "specific factors that could drive the stock price up",
  "price_risks": "specific factors that could drive the stock price down",
  "sentiment_score": <float from -1.0 (very negative) to 1.0 (very positive)>,
  "sentiment_label": "<very_negative|negative|neutral|positive|very_positive>",
  "relevance_score": <float 0.0 to 1.0 - how much this moves the stock>,
  "time_horizon": "<immediate|short_term|medium_term|long_term>",
  "confidence": <float 0.0 to 1.0>
}}

Return ONLY the JSON, no other text."""

    raw = _call_llm(prompt, provider=provider, max_tokens=1024)

    # Try to parse JSON from the response
    result = _parse_json_response(raw)
    result["llm_model"] = _get_model_name(provider)
    result["llm_processed_at"] = datetime.now(timezone.utc).isoformat()

    logger.info("News analyzed", ticker=ticker, provider=provider or settings.LLM_PROVIDER_PRIMARY,
                sentiment=result.get("sentiment_label"))
    return result


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def analyze_earnings_report(
    ticker: str,
    company_name: str,
    fiscal_year: int,
    fiscal_quarter: int,
    metrics: dict,
    provider: str = None,
) -> dict:
    """
    Analyze quarterly earnings using the configured LLM provider.
    """
    metrics_str = json.dumps(metrics, indent=2, default=str)

    prompt = f"""You are a top-tier Wall Street equity analyst. Analyze {company_name} ({ticker})
Q{fiscal_quarter} {fiscal_year} earnings report and provide an institutional-quality assessment.

EARNINGS DATA:
{metrics_str}

Provide your analysis in the following JSON format:
{{
  "summary": "Executive summary of earnings results (3-4 sentences)",
  "bull_case": "3 strongest reasons to be bullish after these results",
  "bear_case": "3 strongest reasons to be cautious after these results",
  "key_metrics": {{
    "eps_beat_miss": "<beat|miss|in_line> with commentary",
    "revenue_beat_miss": "<beat|miss|in_line> with commentary",
    "guidance_tone": "<raised|maintained|lowered|not_provided>",
    "margin_trend": "<expanding|stable|contracting>",
    "quality_of_beat": "<high|medium|low> - was it driven by real business or one-time items"
  }},
  "earnings_quality_score": <1-10, 10 being highest quality results>,
  "price_reaction_prediction": "<strong_up|up|flat|down|strong_down>",
  "key_themes": ["theme 1", "theme 2", "theme 3"],
  "watch_items_next_quarter": ["item 1", "item 2"]
}}

Return ONLY the JSON, no other text."""

    raw = _call_llm(prompt, provider=provider, max_tokens=1500)
    result = _parse_json_response(raw)
    result["llm_model"] = _get_model_name(provider)
    result["llm_processed_at"] = datetime.now(timezone.utc).isoformat()

    logger.info("Earnings analyzed", ticker=ticker, quarter=f"Q{fiscal_quarter} {fiscal_year}",
                provider=provider or settings.LLM_PROVIDER_PRIMARY)
    return result


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def generate_forecast_rationale(
    ticker: str,
    company_name: str,
    forecast_data: dict,
    recent_news_summaries: list[str],
    technical_snapshot: dict,
    provider: str = None,
) -> str:
    """Generate a narrative explanation for a stock forecast."""
    news_text = "\n".join(f"- {s}" for s in recent_news_summaries[:5]) if recent_news_summaries else "No recent news"

    prompt = f"""You are a senior portfolio manager at a top hedge fund. Write a concise,
actionable forecast rationale for {company_name} ({ticker}).

FORECAST DATA:
{json.dumps(forecast_data, indent=2, default=str)}

RECENT NEWS HIGHLIGHTS:
{news_text}

TECHNICAL SNAPSHOT:
{json.dumps(technical_snapshot, indent=2, default=str)}

Write a 3-4 paragraph professional rationale that:
1. States the predicted direction and confidence clearly
2. Identifies the top 2-3 drivers of the forecast
3. Highlights key risks to the thesis
4. Notes any specific catalysts in the near term

Be direct, specific, and actionable. Write like you're briefing a portfolio manager."""

    return _call_llm(prompt, provider=provider, max_tokens=800)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def generate_daily_market_brief(
    top_opportunities: list[dict],
    market_conditions: dict,
    date_str: str,
    provider: str = None,
) -> str:
    """Generate a daily morning market brief highlighting top opportunities."""
    opportunities_str = json.dumps(top_opportunities[:10], indent=2, default=str)
    market_str = json.dumps(market_conditions, indent=2, default=str)

    prompt = f"""You are the Chief Investment Officer of a quantitative hedge fund.
Write a crisp, actionable morning market brief for {date_str}.

MARKET CONDITIONS:
{market_str}

TOP FORECASTED OPPORTUNITIES (ranked by opportunity score):
{opportunities_str}

Write a professional morning brief (5-7 paragraphs) that:
1. Opens with market regime / macro context (VIX, yield curve, sector rotation)
2. Highlights the top 3 long opportunities with specific reasoning
3. Notes any short-selling opportunities or hedging considerations
4. Identifies key risks for the day (earnings, macro data releases, geopolitical)
5. Closes with a risk management note

Format: Professional, concise, data-driven. Use specific numbers. No fluff."""

    return _call_llm(prompt, provider=provider, max_tokens=1200)


# ── Helpers ───────────────────────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict:
    """Parse JSON from LLM response, handling markdown code fences."""
    text = raw.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines if they're fences
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON object from the text
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        logger.warning("Failed to parse LLM JSON response", raw_preview=text[:200])
        return {}


def get_provider_for_ticker(ticker: str) -> str:
    """
    Determine which LLM provider to use for a given ticker.

    Stocks of interest (watchlist) → primary provider (Gemini)
    Other stocks (big movers) → secondary provider (Ollama)
    """
    watchlist = set(settings.watchlist)
    if ticker.upper() in watchlist:
        return settings.LLM_PROVIDER_PRIMARY
    return settings.LLM_PROVIDER_SECONDARY


def is_provider_available(provider: str = None) -> bool:
    """Check if a given LLM provider has the required configuration."""
    provider = provider or settings.LLM_PROVIDER_PRIMARY
    if provider == "gemini":
        return bool(settings.GEMINI_API_KEY)
    elif provider == "ollama":
        # Ollama doesn't need an API key, just check if URL is set
        return bool(settings.OLLAMA_BASE_URL)
    elif provider == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    return False


# ── Backward compatibility ────────────────────────────────────────────────

def get_anthropic_client():
    """Legacy accessor for Anthropic client."""
    return _get_anthropic_client()
