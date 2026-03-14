"""
PortainerPipeline — Portainer container management API integration.
"""
import json
import logging
from datetime import datetime

import requests

from app.config import Config
from app.db import get_conn, log_event

logger = logging.getLogger(__name__)


class PortainerPipeline:
    _jwt: str | None = None

    def _auth(self) -> str:
        if self._jwt:
            return self._jwt
        resp = requests.post(
            f"{Config.PORTAINER_URL}/api/auth",
            json={"username": Config.PORTAINER_USERNAME, "password": Config.PORTAINER_PASSWORD},
            timeout=10, verify=False,
        )
        resp.raise_for_status()
        self.__class__._jwt = resp.json().get("jwt", "")
        return self.__class__._jwt

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._auth()}"}

    def _get(self, path: str) -> dict | list:
        resp = requests.get(
            f"{Config.PORTAINER_URL}/api{path}",
            headers=self._headers(), timeout=10, verify=False,
        )
        if resp.status_code == 401:
            self.__class__._jwt = None  # force re-auth
            resp = requests.get(
                f"{Config.PORTAINER_URL}/api{path}",
                headers=self._headers(), timeout=10, verify=False,
            )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict = None) -> dict | list:
        resp = requests.post(
            f"{Config.PORTAINER_URL}/api{path}",
            headers=self._headers(), json=payload or {}, timeout=10, verify=False,
        )
        resp.raise_for_status()
        return resp.json() if resp.text else {}

    def get_endpoints(self) -> list:
        try:
            return self._get("/endpoints")
        except Exception as e:
            logger.error("Portainer endpoints error: %s", e)
            return []

    def get_summary(self, endpoint_id: int = 1) -> dict:
        if not Config.PORTAINER_URL:
            return {"error": "PORTAINER_URL not configured"}
        try:
            containers = self._get(f"/endpoints/{endpoint_id}/docker/containers/json?all=true")
            running = [c for c in containers if c.get("State") == "running"]
            stopped = [c for c in containers if c.get("State") in ("exited", "stopped", "created")]
            unhealthy = [c for c in running if c.get("Status", "").lower().startswith("unhealthy")]

            container_list = [
                {
                    "id": c.get("Id", "")[:12],
                    "name": (c.get("Names", [""])[0] or "").lstrip("/"),
                    "image": c.get("Image", ""),
                    "state": c.get("State", ""),
                    "status": c.get("Status", ""),
                    "created": c.get("Created", 0),
                }
                for c in containers
            ]

            result = {
                "captured_at": datetime.now().isoformat(),
                "running_count": len(running),
                "stopped_count": len(stopped),
                "total_count": len(containers),
                "unhealthy_count": len(unhealthy),
                "containers": container_list,
            }

            self._save_snapshot(result)

            if unhealthy:
                log_event(
                    "portainer",
                    f"{len(unhealthy)} unhealthy containers",
                    details=", ".join(c.get("name", "") for c in container_list if "unhealthy" in c["status"].lower()),
                    severity="warn",
                )

            return result
        except Exception as e:
            logger.error("PortainerPipeline error: %s", e)
            log_event("portainer", f"Portainer error: {e}", severity="error")
            return {"error": str(e)}

    def container_action(self, endpoint_id: int, container_id: str, action: str) -> dict:
        """action: start | stop | restart | pause | unpause"""
        valid_actions = {"start", "stop", "restart", "pause", "unpause"}
        if action not in valid_actions:
            return {"success": False, "error": f"Invalid action: {action}"}
        try:
            self._post(f"/endpoints/{endpoint_id}/docker/containers/{container_id}/{action}")
            return {"success": True, "action": action, "container": container_id}
        except Exception as e:
            logger.error("Portainer action error: %s", e)
            return {"success": False, "error": str(e)}

    def get_stacks(self) -> list:
        try:
            stacks = self._get("/stacks")
            return [
                {
                    "id": s.get("Id"),
                    "name": s.get("Name", ""),
                    "status": s.get("Status", 0),
                    "endpoint_id": s.get("EndpointId"),
                    "type": s.get("Type"),
                }
                for s in stacks
            ]
        except Exception as e:
            logger.error("Portainer stacks error: %s", e)
            return []

    def _save_snapshot(self, snap: dict):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO portainer_snapshots
                (running_count, stopped_count, total_count, unhealthy_count, containers_json)
                VALUES (%s,%s,%s,%s,%s)
            """, (
                snap["running_count"], snap["stopped_count"],
                snap["total_count"], snap["unhealthy_count"],
                json.dumps(snap["containers"])[:65535],
            ))
            cur.close()
            conn.close()
        except Exception as e:
            logger.error("portainer_snapshots insert failed: %s", e)
