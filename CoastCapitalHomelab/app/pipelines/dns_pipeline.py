"""
DNSPipeline — CoreDNS local DNS server management.

Records are stored in a shared hosts file that CoreDNS watches and
hot-reloads every 15s via its `reload` plugin.  The pipeline manages
that file directly (file-lock protected) and checks server health via
CoreDNS's built-in HTTP health endpoint.
"""
import os
import logging
from datetime import datetime

import requests

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:          # Windows dev environments
    _HAS_FCNTL = False

from app.config import Config
from app.db import log_event

logger = logging.getLogger(__name__)


class DNSPipeline:

    # ── Internals ──────────────────────────────────────────────────────────

    def _hosts_path(self) -> str:
        return Config.DNS_HOSTS_FILE

    def _check_health(self) -> bool:
        try:
            resp = requests.get(Config.DNS_HEALTH_URL, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _read_lines(self) -> list[str]:
        path = self._hosts_path()
        if not os.path.exists(path):
            return []
        with open(path, "r") as f:
            return f.readlines()

    def _write_lines(self, lines: list[str]):
        path = self._hosts_path()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            if _HAS_FCNTL:
                fcntl.flock(f, fcntl.LOCK_EX)
            f.writelines(lines)
            if _HAS_FCNTL:
                fcntl.flock(f, fcntl.LOCK_UN)

    # ── Public API ─────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Status, record count, and upstream servers."""
        if not Config.DNS_HOSTS_FILE:
            return {"error": "DNS_HOSTS_FILE not configured"}
        healthy = self._check_health()
        records = self.get_records()
        return {
            "captured_at": datetime.now().isoformat(),
            "status": "online" if healthy else "offline",
            "record_count": len(records),
            "upstream": Config.DNS_UPSTREAM,
        }

    def get_records(self) -> list:
        """Return all custom A records as [{ip, domain}]."""
        records = []
        try:
            for line in self._read_lines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    records.append({"ip": parts[0], "domain": parts[1]})
        except Exception as e:
            logger.error("DNSPipeline.get_records error: %s", e)
        return records

    def add_record(self, ip: str, domain: str) -> dict:
        """Append a new A record to the hosts file."""
        ip     = ip.strip()
        domain = domain.strip().lower()
        if not ip or not domain:
            return {"success": False, "error": "ip and domain are required"}

        # Prevent duplicates
        existing = self.get_records()
        for r in existing:
            if r["domain"] == domain and r["ip"] == ip:
                return {"success": False, "error": f"{domain} → {ip} already exists"}

        try:
            path = self._hosts_path()
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "a") as f:
                if _HAS_FCNTL:
                    fcntl.flock(f, fcntl.LOCK_EX)
                f.write(f"{ip} {domain}\n")
                if _HAS_FCNTL:
                    fcntl.flock(f, fcntl.LOCK_UN)
            log_event("dns", f"DNS record added: {domain} → {ip}")
            return {"success": True, "ip": ip, "domain": domain}
        except Exception as e:
            logger.error("DNSPipeline.add_record error: %s", e)
            return {"success": False, "error": str(e)}

    def delete_record(self, ip: str, domain: str) -> dict:
        """Remove an A record from the hosts file."""
        ip     = ip.strip()
        domain = domain.strip().lower()
        target = f"{ip} {domain}"
        try:
            lines     = self._read_lines()
            new_lines = [l for l in lines if l.strip() != target and l.strip()]
            # Always preserve the header comment block
            header = [l for l in lines if l.startswith("#")]
            data   = [l for l in new_lines if not l.startswith("#")]
            self._write_lines(header + data)
            log_event("dns", f"DNS record deleted: {domain} → {ip}")
            return {"success": True}
        except Exception as e:
            logger.error("DNSPipeline.delete_record error: %s", e)
            return {"success": False, "error": str(e)}
