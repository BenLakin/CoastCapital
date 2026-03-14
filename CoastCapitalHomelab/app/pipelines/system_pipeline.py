"""
SystemPipeline — SSH-based health monitoring for multiple machines.

Supports two target types:
  - mac    : SSH to host.docker.internal; runs macOS top/vm_stat/df. No nvidia-smi.
  - ubuntu : SSH to SERVER_HOST; runs Linux top/df + nvidia-smi for Nvidia GPU.

Each snapshot is tagged with machine_name, machine_type, and machine_desc.
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import paramiko

from app.config import Config
from app.db import get_conn, log_event

logger = logging.getLogger(__name__)


@dataclass
class MachineTarget:
    name: str          # display name, e.g. "Mac Studio"
    machine_type: str  # "mac" | "ubuntu"
    desc: str          # description, e.g. "Docker Host · macOS"
    host: str          # SSH hostname/IP
    user: str          # SSH username
    ssh_key: str       # path to private key (empty string = use password)
    ssh_password: str  # password auth if no key


class SystemPipeline:

    # ── SSH plumbing ──────────────────────────────────────────────────────────

    def _connect(self, target: MachineTarget) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = dict(hostname=target.host, username=target.user, timeout=15)
        if target.ssh_password:
            kwargs["password"] = target.ssh_password
        elif target.ssh_key:
            kwargs["key_filename"] = target.ssh_key
        client.connect(**kwargs)
        return client

    def _exec(self, client: paramiko.SSHClient, cmd: str) -> str:
        _, stdout, stderr = client.exec_command(cmd, timeout=30)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if err.strip():
            logger.debug("ssh stderr for %r: %s", cmd[:60], err[:200])
        return out

    # ── macOS parsers ─────────────────────────────────────────────────────────

    def _mac_stats(self, client: paramiko.SSHClient) -> dict:
        """Collect CPU, memory, disk, and load from a macOS host."""
        result = {
            "raw": "", "cpu_pct": None, "mem_pct": None,
            "disk_pct": None, "load_1": None, "load_5": None, "load_15": None,
        }

        # top -l 1 -n 0 -s 0  (1 sample, 0 processes, 0s delay)
        raw = self._exec(client, "top -l 1 -n 0 -s 0 2>/dev/null")
        result["raw"] = raw

        # Load average: "Load Avg: 1.23, 0.98, 0.87"
        m = re.search(r"Load Avg:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", raw)
        if m:
            result["load_1"] = float(m.group(1))
            result["load_5"] = float(m.group(2))
            result["load_15"] = float(m.group(3))

        # CPU: "CPU usage: 12.50% user, 8.30% sys, 79.20% idle"
        m = re.search(r"CPU usage:\s*[\d.]+%\s*user,\s*[\d.]+%\s*sys,\s*([\d.]+)%\s*idle", raw)
        if m:
            result["cpu_pct"] = round(100.0 - float(m.group(1)), 1)

        # Memory: "PhysMem: 26G used (...), 6016M unused"
        m = re.search(
            r"PhysMem:\s*([\d.]+)([GMKT])\s+used.*?,\s*([\d.]+)([GMKT])\s+unused",
            raw, re.IGNORECASE,
        )
        if m:
            def to_mb(val, unit):
                unit = unit.upper()
                v = float(val)
                return v * 1024 if unit == "G" else v * 1048576 if unit == "T" else v * 0.001 if unit == "K" else v

            used_mb   = to_mb(m.group(1), m.group(2))
            unused_mb = to_mb(m.group(3), m.group(4))
            total_mb  = used_mb + unused_mb
            if total_mb > 0:
                result["mem_pct"] = round(used_mb / total_mb * 100, 1)

        # Disk: df -h / — same format as Linux
        df_raw = self._exec(client, "df -h / | tail -1")
        m = re.search(r"(\d+)%", df_raw)
        if m:
            result["disk_pct"] = float(m.group(1))

        return result

    # ── Linux parsers ─────────────────────────────────────────────────────────

    def _linux_stats(self, client: paramiko.SSHClient) -> dict:
        """Collect CPU, memory, disk, and load from a Linux host via top."""
        result = {
            "raw": "", "cpu_pct": None, "mem_pct": None,
            "disk_pct": None, "load_1": None, "load_5": None, "load_15": None,
        }
        raw = self._exec(client, "top -b -n 1 -d 0.5")
        result["raw"] = raw

        # Load average
        m = re.search(r"load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", raw)
        if m:
            result["load_1"] = float(m.group(1))
            result["load_5"] = float(m.group(2))
            result["load_15"] = float(m.group(3))

        # CPU idle → usage
        m = re.search(r"%Cpu.*?(\d+[\.,]\d+)\s*id", raw)
        if m:
            result["cpu_pct"] = round(100.0 - float(m.group(1).replace(",", ".")), 1)

        # Memory: "MiB Mem : total ... free ... used"
        m = re.search(
            r"MiB Mem\s*:\s*([\d.]+)\s*total.*?([\d.]+)\s*free.*?([\d.]+)\s*used",
            raw,
        )
        if m:
            total, _free, used = float(m.group(1)), float(m.group(2)), float(m.group(3))
            if total > 0:
                result["mem_pct"] = round(used / total * 100, 1)

        # Disk
        df_raw = self._exec(client, "df -h / | tail -1")
        m = re.search(r"(\d+)%", df_raw)
        if m:
            result["disk_pct"] = float(m.group(1))

        return result

    def _nvidia_smi(self, client: paramiko.SSHClient) -> dict:
        """Query Nvidia GPU via nvidia-smi. Returns nulls if no GPU present."""
        result = {
            "raw": "", "gpu_name": None, "gpu_util": None,
            "gpu_mem_used_mb": None, "gpu_mem_total_mb": None, "gpu_temp": None,
        }
        raw = self._exec(
            client,
            "nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu "
            "--format=csv,noheader,nounits 2>/dev/null || echo NO_GPU",
        )
        result["raw"] = raw
        if "NO_GPU" in raw or not raw.strip():
            return result
        parts = [p.strip() for p in raw.strip().split(",")]
        if len(parts) >= 5:
            result["gpu_name"] = parts[0]
            result["gpu_util"] = float(parts[1]) if parts[1] else None
            result["gpu_mem_used_mb"] = int(parts[2]) if parts[2] else None
            result["gpu_mem_total_mb"] = int(parts[3]) if parts[3] else None
            result["gpu_temp"] = float(parts[4]) if parts[4] else None
        return result

    # ── Machine-level poll ────────────────────────────────────────────────────

    def _poll_machine(self, target: MachineTarget) -> dict:
        """Connect to a machine, collect stats, persist snapshot, return dict."""
        client = self._connect(target)
        try:
            if target.machine_type == "mac":
                stats = self._mac_stats(client)
                gpu   = {"raw": "", "gpu_name": None, "gpu_util": None,
                         "gpu_mem_used_mb": None, "gpu_mem_total_mb": None, "gpu_temp": None}
            else:  # ubuntu / linux
                stats = self._linux_stats(client)
                gpu   = self._nvidia_smi(client)
        finally:
            client.close()

        snapshot = {
            "captured_at":     datetime.now().isoformat(),
            "machine_name":    target.name,
            "machine_type":    target.machine_type,
            "machine_desc":    target.desc,
            "cpu_pct":         stats["cpu_pct"],
            "mem_pct":         stats["mem_pct"],
            "disk_pct":        stats["disk_pct"],
            "load_1":          stats["load_1"],
            "load_5":          stats["load_5"],
            "load_15":         stats["load_15"],
            "gpu_name":        gpu["gpu_name"],
            "gpu_util":        gpu["gpu_util"],
            "gpu_mem_used_mb": gpu["gpu_mem_used_mb"],
            "gpu_mem_total_mb":gpu["gpu_mem_total_mb"],
            "gpu_temp":        gpu["gpu_temp"],
        }

        self._save_snapshot(snapshot, stats["raw"], gpu["raw"])
        self._check_alerts(snapshot)
        return snapshot

    def _check_alerts(self, snap: dict):
        name = snap["machine_name"]
        if snap.get("cpu_pct") and snap["cpu_pct"] > 90:
            log_event("system", f"[{name}] High CPU: {snap['cpu_pct']}%", severity="warn")
        if snap.get("mem_pct") and snap["mem_pct"] > 90:
            log_event("system", f"[{name}] High Memory: {snap['mem_pct']}%", severity="warn")
        if snap.get("gpu_temp") and snap["gpu_temp"] > 85:
            log_event("system", f"[{name}] High GPU temp: {snap['gpu_temp']}°C", severity="warn")

    # ── Target factories ──────────────────────────────────────────────────────

    def _local_target(self) -> Optional[MachineTarget]:
        if not Config.MONITOR_LOCAL or not Config.LOCAL_USER:
            return None
        return MachineTarget(
            name=Config.LOCAL_MACHINE_NAME,
            machine_type="mac",
            desc=Config.LOCAL_MACHINE_DESC,
            host=Config.LOCAL_HOST,
            user=Config.LOCAL_USER,
            ssh_key=Config.LOCAL_SSH_KEY,
            ssh_password=Config.LOCAL_SSH_PASSWORD,
        )

    def _remote_target(self) -> Optional[MachineTarget]:
        if not Config.SERVER_HOST:
            return None
        return MachineTarget(
            name=Config.SERVER_NAME,
            machine_type="ubuntu",
            desc=Config.SERVER_DESC,
            host=Config.SERVER_HOST,
            user=Config.SERVER_USER,
            ssh_key=Config.SERVER_SSH_KEY,
            ssh_password=Config.SERVER_SSH_PASSWORD,
        )

    def _extra_targets(self) -> list[MachineTarget]:
        """Parse EXTRA_MACHINES env var (JSON array) into MachineTarget objects.

        Each entry: {"name": "...", "type": "mac|ubuntu", "desc": "...",
                     "host": "...", "user": "...", "ssh_key": "...", "ssh_password": "..."}
        """
        raw = Config.EXTRA_MACHINES
        if not raw or not raw.strip():
            return []
        try:
            machines = json.loads(raw)
            if not isinstance(machines, list):
                logger.warning("EXTRA_MACHINES is not a JSON array, skipping")
                return []
            targets = []
            for m in machines:
                targets.append(MachineTarget(
                    name=m.get("name", "Unknown"),
                    machine_type=m.get("type", "ubuntu"),
                    desc=m.get("desc", ""),
                    host=m.get("host", ""),
                    user=m.get("user", "ubuntu"),
                    ssh_key=m.get("ssh_key", ""),
                    ssh_password=m.get("ssh_password", ""),
                ))
            return targets
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("Failed to parse EXTRA_MACHINES: %s", e)
            return []

    # ── Public API ────────────────────────────────────────────────────────────

    def get_local_health(self) -> dict:
        """Poll the local Mac (Docker host) via SSH."""
        target = self._local_target()
        if target is None:
            return {"error": "Local monitoring not configured (set LOCAL_USER and LOCAL_HOST)"}
        try:
            return self._poll_machine(target)
        except Exception as e:
            logger.error("Local SSH error: %s", e)
            log_event("system", f"[{Config.LOCAL_MACHINE_NAME}] SSH failed: {e}", severity="error")
            return {"error": str(e), "machine_name": Config.LOCAL_MACHINE_NAME, "machine_type": "mac"}

    def get_remote_health(self) -> dict:
        """Poll the remote Ubuntu server via SSH."""
        target = self._remote_target()
        if target is None:
            return {"error": "SERVER_HOST not configured"}
        try:
            return self._poll_machine(target)
        except Exception as e:
            logger.error("Remote SSH error: %s", e)
            log_event("system", f"[{Config.SERVER_NAME}] SSH failed: {e}", severity="error")
            return {"error": str(e), "machine_name": Config.SERVER_NAME, "machine_type": "ubuntu"}

    def get_all_machines(self) -> list[dict]:
        """Poll all configured machines and return a list of snapshots."""
        results = []
        targets = [t for t in [self._local_target(), self._remote_target()] if t is not None]
        targets.extend(self._extra_targets())
        if not targets:
            return [{"error": "No machines configured"}]
        for target in targets:
            try:
                results.append(self._poll_machine(target))
            except Exception as e:
                logger.error("Machine %s error: %s", target.name, e)
                results.append({
                    "error": str(e),
                    "machine_name": target.name,
                    "machine_type": target.machine_type,
                    "machine_desc": target.desc,
                })
        return results

    def get_system_health(self, machine: str = "all") -> dict | list:
        """
        Dispatch by machine selector.
          machine='all'    → list of all machines (default)
          machine='local'  → Mac only
          machine='remote' → Ubuntu only
        """
        if machine == "local":
            return self.get_local_health()
        if machine == "remote":
            return self.get_remote_health()
        return self.get_all_machines()

    # ── Database ──────────────────────────────────────────────────────────────

    def _save_snapshot(self, snap: dict, raw_top: str, raw_nvidia: str):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO system_snapshots
                (machine_name, machine_type, machine_desc,
                 cpu_pct, mem_pct, disk_pct, load_1, load_5, load_15,
                 gpu_name, gpu_util, gpu_mem_used_mb, gpu_mem_total_mb, gpu_temp,
                 raw_top, raw_nvidia)
                VALUES (%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s)
            """, (
                snap["machine_name"], snap["machine_type"], snap.get("machine_desc"),
                snap["cpu_pct"], snap["mem_pct"], snap["disk_pct"],
                snap["load_1"], snap["load_5"], snap["load_15"],
                snap["gpu_name"], snap["gpu_util"],
                snap["gpu_mem_used_mb"], snap["gpu_mem_total_mb"], snap["gpu_temp"],
                raw_top[:65535], raw_nvidia[:65535],
            ))
            cur.close()
            conn.close()
        except Exception as e:
            logger.error("system_snapshots insert failed: %s", e)

    def get_history(self, limit: int = 24, machine_name: str = None) -> list:
        """Return recent snapshots. Optionally filter by machine_name."""
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            if machine_name:
                cur.execute("""
                    SELECT captured_at, machine_name, machine_type, machine_desc,
                           cpu_pct, mem_pct, disk_pct, load_1, load_5, load_15,
                           gpu_name, gpu_util, gpu_mem_used_mb, gpu_mem_total_mb, gpu_temp
                    FROM system_snapshots
                    WHERE machine_name = %s
                    ORDER BY captured_at DESC LIMIT %s
                """, (machine_name, limit))
            else:
                cur.execute("""
                    SELECT captured_at, machine_name, machine_type, machine_desc,
                           cpu_pct, mem_pct, disk_pct, load_1, load_5, load_15,
                           gpu_name, gpu_util, gpu_mem_used_mb, gpu_mem_total_mb, gpu_temp
                    FROM system_snapshots
                    ORDER BY captured_at DESC LIMIT %s
                """, (limit,))
            rows = cur.fetchall()
            cur.close()
            conn.close()
            for r in rows:
                if r.get("captured_at"):
                    r["captured_at"] = r["captured_at"].isoformat()
            return rows
        except Exception as e:
            logger.error("system history error: %s", e)
            return []
