"""
HomepagePipeline — Homepage dashboard integration.
Fetches service widget status from a Homepage instance.
"""
import logging
from datetime import datetime

import requests

from app.config import Config

logger = logging.getLogger(__name__)


class HomepagePipeline:
    def get_status(self) -> dict:
        if not Config.HOMEPAGE_URL:
            return {"status": "not_configured", "message": "HOMEPAGE_URL not set"}
        try:
            resp = requests.get(
                f"{Config.HOMEPAGE_URL.rstrip('/')}/api/widgets",
                timeout=10,
            )
            if resp.status_code == 404:
                # Homepage may not expose this endpoint — fall back to basic health
                resp = requests.get(Config.HOMEPAGE_URL, timeout=10)
                return {
                    "reachable": resp.status_code < 400,
                    "status_code": resp.status_code,
                    "url": Config.HOMEPAGE_URL,
                    "captured_at": datetime.now().isoformat(),
                }
            resp.raise_for_status()
            return {
                "reachable": True,
                "widgets": resp.json(),
                "captured_at": datetime.now().isoformat(),
            }
        except requests.exceptions.ConnectionError:
            return {"reachable": False, "error": "Connection refused", "url": Config.HOMEPAGE_URL}
        except Exception as e:
            logger.error("HomepagePipeline error: %s", e)
            return {"reachable": False, "error": str(e)}

    def health_check(self) -> bool:
        try:
            resp = requests.get(Config.HOMEPAGE_URL or "http://localhost", timeout=5)
            return resp.status_code < 500
        except Exception:
            return False
