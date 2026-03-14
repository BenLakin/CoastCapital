"""
HomeAssistantPipeline — Home Assistant REST API integration.
"""
import json
import logging
from datetime import datetime

import requests

from app.config import Config
from app.db import get_conn, log_event

logger = logging.getLogger(__name__)


class HomeAssistantPipeline:
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {Config.HA_TOKEN}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> dict | list:
        url = f"{Config.HA_URL}/api{path}"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{Config.HA_URL}/api{path}"
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_summary(self) -> dict:
        if not Config.HA_URL or not Config.HA_TOKEN:
            return {"error": "HA_URL or HA_TOKEN not configured"}
        try:
            states = self._get("/states")
            entities = states if isinstance(states, list) else []

            # Count automations on
            automations_on = sum(
                1 for e in entities
                if e.get("entity_id", "").startswith("automation.") and e.get("state") == "on"
            )

            # Collect alerts: unavailable/unknown + persistent notifications
            alerts = []
            for e in entities:
                if e.get("state") in ("unavailable", "unknown"):
                    alerts.append({
                        "entity_id": e.get("entity_id"),
                        "state": e.get("state"),
                        "name": e.get("attributes", {}).get("friendly_name", e.get("entity_id")),
                    })

            # Persistent notifications
            try:
                notifs = self._get("/states")
                for e in entities:
                    if e.get("entity_id", "").startswith("persistent_notification."):
                        alerts.append({
                            "entity_id": e.get("entity_id"),
                            "state": "notification",
                            "name": e.get("attributes", {}).get("title", "Notification"),
                            "message": e.get("attributes", {}).get("message", ""),
                        })
            except Exception:
                pass

            result = {
                "captured_at": datetime.now().isoformat(),
                "entity_count": len(entities),
                "automations_on": automations_on,
                "alert_count": len(alerts),
                "alerts": alerts[:20],
            }

            self._save_snapshot(result, json.dumps({"entity_count": len(entities)}))

            if alerts:
                log_event("home_assistant", f"{len(alerts)} alerts/unavailable entities", severity="warn")

            return result
        except Exception as e:
            logger.error("HomeAssistantPipeline error: %s", e)
            log_event("home_assistant", f"HA error: {e}", severity="error")
            return {"error": str(e)}

    def get_entities(self, domain: str = None) -> list:
        try:
            states = self._get("/states")
            entities = states if isinstance(states, list) else []
            if domain:
                entities = [e for e in entities if e.get("entity_id", "").startswith(f"{domain}.")]
            return [
                {
                    "entity_id": e.get("entity_id"),
                    "state": e.get("state"),
                    "name": e.get("attributes", {}).get("friendly_name", e.get("entity_id")),
                    "unit": e.get("attributes", {}).get("unit_of_measurement", ""),
                }
                for e in entities
            ]
        except Exception as e:
            logger.error("HA entities error: %s", e)
            return []

    def call_service(self, domain: str, service: str, entity_id: str, extra: dict = None) -> dict:
        payload = {"entity_id": entity_id}
        if extra:
            payload.update(extra)
        try:
            result = self._post(f"/services/{domain}/{service}", payload)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error("HA service call error: %s", e)
            return {"success": False, "error": str(e)}

    def get_history(self, entity_id: str, hours: int = 24) -> list:
        try:
            data = self._get(f"/history/period?filter_entity_id={entity_id}&minimal_response=true")
            return data[0] if data and isinstance(data, list) else []
        except Exception as e:
            logger.error("HA history error: %s", e)
            return []

    def _save_snapshot(self, snap: dict, raw_json: str):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO homeassistant_snapshots
                (entity_count, alert_count, automations_on, alerts_json, raw_json)
                VALUES (%s,%s,%s,%s,%s)
            """, (
                snap["entity_count"], snap["alert_count"], snap["automations_on"],
                json.dumps(snap["alerts"])[:65535], raw_json[:65535],
            ))
            cur.close()
            conn.close()
        except Exception as e:
            logger.error("homeassistant_snapshots insert failed: %s", e)
