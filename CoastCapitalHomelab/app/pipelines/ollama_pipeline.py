"""
OllamaPipeline — Ollama local AI server integration.
"""
import json
import logging
from datetime import datetime

import requests

from app.config import Config
from app.db import get_conn, log_event

logger = logging.getLogger(__name__)


class OllamaPipeline:
    def _base(self) -> str:
        return Config.OLLAMA_BASE_URL.rstrip("/")

    def get_summary(self) -> dict:
        if not Config.OLLAMA_BASE_URL:
            return {"error": "OLLAMA_BASE_URL not configured"}
        try:
            resp = requests.get(f"{self._base()}/api/tags", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            result = {
                "captured_at": datetime.now().isoformat(),
                "models_count": len(models),
                "models": [
                    {
                        "name": m.get("name", ""),
                        "size_gb": round(m.get("size", 0) / 1e9, 2),
                        "modified_at": m.get("modified_at", ""),
                        "family": m.get("details", {}).get("family", ""),
                        "parameters": m.get("details", {}).get("parameter_size", ""),
                        "quantization": m.get("details", {}).get("quantization_level", ""),
                    }
                    for m in models
                ],
            }
            self._save_snapshot(result)
            return result
        except Exception as e:
            logger.error("OllamaPipeline error: %s", e)
            log_event("ollama", f"Ollama error: {e}", severity="error")
            return {"error": str(e)}

    def get_running(self) -> list:
        try:
            resp = requests.get(f"{self._base()}/api/ps", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "name": m.get("name", ""),
                    "size_gb": round(m.get("size", 0) / 1e9, 2),
                    "expires_at": m.get("expires_at", ""),
                }
                for m in data.get("models", [])
            ]
        except Exception as e:
            logger.error("Ollama running error: %s", e)
            return []

    def pull_model(self, model_name: str) -> dict:
        try:
            resp = requests.post(
                f"{self._base()}/api/pull",
                json={"name": model_name, "stream": False},
                timeout=300,
            )
            resp.raise_for_status()
            return {"success": True, "status": resp.json().get("status", "")}
        except Exception as e:
            logger.error("Ollama pull error: %s", e)
            return {"success": False, "error": str(e)}

    def generate(self, model: str, prompt: str, stream: bool = False) -> str:
        try:
            resp = requests.post(
                f"{self._base()}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            logger.error("Ollama generate error: %s", e)
            return f"Error: {e}"

    def _save_snapshot(self, snap: dict):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO ollama_snapshots (models_count, models_json)
                VALUES (%s, %s)
            """, (snap["models_count"], json.dumps(snap["models"])[:65535]))
            cur.close()
            conn.close()
        except Exception as e:
            logger.error("ollama_snapshots insert failed: %s", e)
