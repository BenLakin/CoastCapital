"""
UniFiPipeline — UniFi Network + Protect API integration.
Handles both UniFi OS (UDM/UDM Pro) and classic UniFi controllers.
"""
import json
import logging
from datetime import datetime

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from app.config import Config
from app.db import get_conn, log_event

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logger = logging.getLogger(__name__)


class UniFiPipeline:
    def __init__(self):
        self.base = f"https://{Config.UNIFI_HOST}:{Config.UNIFI_PORT}"
        self.site = Config.UNIFI_SITE
        self._session: requests.Session | None = None

    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        s = requests.Session()
        s.verify = False
        # Try UniFi OS login (UDM/UDM Pro)
        resp = s.post(f"{self.base}/api/auth/login", json={
            "username": Config.UNIFI_USERNAME,
            "password": Config.UNIFI_PASSWORD,
        }, timeout=10)
        if resp.status_code == 200:
            logger.debug("UniFi OS login OK")
            self._session = s
            return s
        # Fallback: classic controller login
        resp = s.post(f"{self.base}/api/login", json={
            "username": Config.UNIFI_USERNAME,
            "password": Config.UNIFI_PASSWORD,
        }, timeout=10)
        resp.raise_for_status()
        logger.debug("UniFi classic login OK")
        self._session = s
        return s

    def _get(self, path: str) -> dict:
        s = self._get_session()
        resp = s.get(f"{self.base}{path}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ── Network ───────────────────────────────────────────────────────────────

    def get_network_stats(self) -> dict:
        if not Config.UNIFI_HOST:
            return {"error": "UNIFI_HOST not configured"}
        try:
            # Site stat
            stat = self._get(f"/proxy/network/api/s/{self.site}/stat/sysinfo")
            health = self._get(f"/proxy/network/api/s/{self.site}/stat/health")
            clients = self._get(f"/proxy/network/api/s/{self.site}/stat/sta")

            wan = {}
            for entry in health.get("data", []):
                if entry.get("subsystem") == "wan":
                    wan = entry
                    break

            wifi_clients = sum(1 for c in clients.get("data", []) if not c.get("is_wired", False))
            wired_clients = sum(1 for c in clients.get("data", []) if c.get("is_wired", False))

            result = {
                "captured_at": datetime.now().isoformat(),
                "wan_ip": wan.get("wan_ip", ""),
                "isp_name": wan.get("isp_name", ""),
                "wan_rx_bytes": wan.get("rx_bytes", 0),
                "wan_tx_bytes": wan.get("tx_bytes", 0),
                "wan_speed_mbps": round((wan.get("rx_bytes-r", 0) + wan.get("tx_bytes-r", 0)) * 8 / 1e6, 2),
                "clients_wifi": wifi_clients,
                "clients_wired": wired_clients,
                "uptime_sec": stat.get("data", [{}])[0].get("uptime", 0),
                "alerts_count": 0,
            }

            self._save_snapshot(result, json.dumps(health.get("data", [])))
            return result
        except Exception as e:
            logger.error("UniFi network error: %s", e)
            self._session = None  # force re-auth next call
            log_event("unifi", f"Network stats error: {e}", severity="error")
            return {"error": str(e)}

    def get_clients(self) -> list:
        try:
            data = self._get(f"/proxy/network/api/s/{self.site}/stat/sta")
            return [
                {
                    "hostname": c.get("hostname", c.get("name", "unknown")),
                    "ip": c.get("ip", ""),
                    "mac": c.get("mac", ""),
                    "is_wired": c.get("is_wired", False),
                    "signal": c.get("signal", None),
                    "tx_bytes": c.get("tx_bytes", 0),
                    "rx_bytes": c.get("rx_bytes", 0),
                    "uptime": c.get("uptime", 0),
                    "oui": c.get("oui", ""),
                }
                for c in data.get("data", [])
            ]
        except Exception as e:
            logger.error("UniFi clients error: %s", e)
            return []

    def get_devices(self) -> list:
        try:
            data = self._get(f"/proxy/network/api/s/{self.site}/stat/device")
            return [
                {
                    "name": d.get("name", d.get("hostname", "")),
                    "model": d.get("model", ""),
                    "state": d.get("state", 0),
                    "uptime": d.get("uptime", 0),
                    "cpu_pct": d.get("system-stats", {}).get("cpu", None),
                    "mem_pct": d.get("system-stats", {}).get("mem", None),
                    "version": d.get("version", ""),
                }
                for d in data.get("data", [])
            ]
        except Exception as e:
            logger.error("UniFi devices error: %s", e)
            return []

    def get_alerts(self) -> list:
        try:
            data = self._get(f"/proxy/network/api/s/{self.site}/stat/alarm")
            alerts = []
            for a in data.get("data", [])[:20]:
                if not a.get("archived", False):
                    alerts.append({
                        "key": a.get("key", ""),
                        "msg": a.get("msg", ""),
                        "datetime": a.get("datetime", ""),
                    })
            return alerts
        except Exception as e:
            logger.error("UniFi alerts error: %s", e)
            return []

    # ── Protect (security cameras) ────────────────────────────────────────────

    def get_protect_summary(self) -> dict:
        try:
            data = self._get("/proxy/protect/api/bootstrap")
            cameras = data.get("cameras", [])
            return {
                "camera_count": len(cameras),
                "cameras": [
                    {
                        "id": c.get("id", ""),
                        "name": c.get("name", ""),
                        "state": c.get("state", ""),
                        "is_recording": c.get("isRecording", False),
                        "is_connected": c.get("isConnected", False),
                        "model": c.get("type", ""),
                    }
                    for c in cameras
                ],
            }
        except Exception as e:
            logger.error("UniFi Protect error: %s", e)
            return {"error": str(e), "camera_count": 0, "cameras": []}

    def get_camera_snapshot(self, camera_id: str) -> bytes:
        """Fetch a JPEG snapshot from UniFi Protect for the given camera ID."""
        if not Config.UNIFI_HOST:
            raise ValueError("UNIFI_HOST not configured")
        s = self._get_session()
        url = f"{self.base}/proxy/protect/api/cameras/{camera_id}/snapshot"
        resp = s.get(url, timeout=15, params={"ts": int(datetime.now().timestamp() * 1000), "highQuality": "false"})
        resp.raise_for_status()
        return resp.content

    def _save_snapshot(self, snap: dict, raw_json: str):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO unifi_snapshots
                (wan_rx_bytes, wan_tx_bytes, wan_speed_mbps, clients_wifi, clients_wired,
                 alerts_count, uptime_sec, wan_ip, isp_name, raw_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                snap.get("wan_rx_bytes"), snap.get("wan_tx_bytes"), snap.get("wan_speed_mbps"),
                snap.get("clients_wifi"), snap.get("clients_wired"), snap.get("alerts_count"),
                snap.get("uptime_sec"), snap.get("wan_ip"), snap.get("isp_name"),
                raw_json[:65535],
            ))
            cur.close()
            conn.close()
        except Exception as e:
            logger.error("unifi_snapshots insert failed: %s", e)
