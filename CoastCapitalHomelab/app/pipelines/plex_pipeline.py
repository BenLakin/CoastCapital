"""
PlexPipeline — Plex Media Server integration via XML API.
"""
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from app.config import Config
from app.db import get_conn, log_event

logger = logging.getLogger(__name__)


class PlexPipeline:
    def _headers(self) -> dict:
        return {
            "X-Plex-Token": Config.PLEX_TOKEN,
            "Accept": "application/json",
        }

    def _get(self, path: str, as_json: bool = True):
        url = f"{Config.PLEX_URL}{path}"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        if as_json:
            return resp.json()
        return resp.text

    def get_summary(self) -> dict:
        if not Config.PLEX_URL or not Config.PLEX_TOKEN:
            return {"error": "PLEX_URL or PLEX_TOKEN not configured"}
        try:
            # Sessions (now playing)
            sessions_data = self._get("/status/sessions")
            sessions = sessions_data.get("MediaContainer", {})
            active_streams = int(sessions.get("size", 0))
            now_playing = []
            for item in sessions.get("Metadata", []):
                user = item.get("User", {}).get("title", "unknown")
                media_type = item.get("type", "")
                title = item.get("grandparentTitle", item.get("title", ""))
                subtitle = item.get("title", "") if media_type == "episode" else ""
                player = item.get("Player", {}).get("title", "")
                state = item.get("Player", {}).get("state", "")
                now_playing.append({
                    "user": user,
                    "type": media_type,
                    "title": title,
                    "subtitle": subtitle,
                    "player": player,
                    "state": state,
                })

            # Libraries
            libs = self._get("/library/sections")
            total_movies = total_shows = total_music = 0
            for lib in libs.get("MediaContainer", {}).get("Directory", []):
                lib_type = lib.get("type")
                lib_key = lib.get("key")
                try:
                    count_data = self._get(f"/library/sections/{lib_key}/all?X-Plex-Container-Size=0&X-Plex-Container-Start=0")
                    count = int(count_data.get("MediaContainer", {}).get("totalSize", 0))
                    if lib_type == "movie":
                        total_movies += count
                    elif lib_type == "show":
                        total_shows += count
                    elif lib_type == "artist":
                        total_music += count
                except Exception:
                    pass

            result = {
                "captured_at": datetime.now().isoformat(),
                "active_streams": active_streams,
                "total_movies": total_movies,
                "total_shows": total_shows,
                "total_music": total_music,
                "now_playing": now_playing,
            }
            self._save_snapshot(result)
            return result
        except Exception as e:
            logger.error("PlexPipeline error: %s", e)
            log_event("plex", f"Plex error: {e}", severity="error")
            return {"error": str(e)}

    def get_recent(self, limit: int = 10) -> list:
        try:
            data = self._get(f"/library/recentlyAdded?X-Plex-Container-Size={limit}")
            items = []
            for item in data.get("MediaContainer", {}).get("Metadata", [])[:limit]:
                items.append({
                    "title": item.get("grandparentTitle", item.get("title", "")),
                    "subtitle": item.get("title", ""),
                    "type": item.get("type", ""),
                    "year": item.get("year", ""),
                    "added_at": item.get("addedAt", ""),
                    "library": item.get("librarySectionTitle", ""),
                })
            return items
        except Exception as e:
            logger.error("Plex recent error: %s", e)
            return []

    def _save_snapshot(self, snap: dict):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO plex_snapshots
                (active_streams, total_movies, total_shows, total_music, now_playing, raw_json)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                snap["active_streams"], snap["total_movies"], snap["total_shows"],
                snap["total_music"],
                json.dumps(snap["now_playing"])[:65535],
                json.dumps(snap)[:65535],
            ))
            cur.close()
            conn.close()
        except Exception as e:
            logger.error("plex_snapshots insert failed: %s", e)
