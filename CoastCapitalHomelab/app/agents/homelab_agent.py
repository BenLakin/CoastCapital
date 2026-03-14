"""
HomeLabAgent — Claude-powered HomeLab developer and operations assistant.

Objective: Develop tools and provide management capabilities for the home lab
infrastructure including internet (UniFi), home security (UniFi Protect),
system health (Mac + Ubuntu), media (Plex), containers (Portainer), AI (Ollama),
DNS (CoreDNS), and home automation (Home Assistant).
"""
import json
import logging
from datetime import datetime

import anthropic

from app.config import Config
from app.pipelines.system_pipeline import SystemPipeline
from app.pipelines.unifi_pipeline import UniFiPipeline
from app.pipelines.plex_pipeline import PlexPipeline
from app.pipelines.homeassistant_pipeline import HomeAssistantPipeline
from app.pipelines.ollama_pipeline import OllamaPipeline
from app.pipelines.dns_pipeline import DNSPipeline
from app.pipelines.portainer_pipeline import PortainerPipeline
from app.pipelines.homepage_pipeline import HomepagePipeline

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are HomeLabAgent, the dedicated HomeLab developer and operations AI for your owner's home lab.

MISSION:
Build tools, monitor services, diagnose issues, and help manage a comprehensive home lab stack.
Be the expert operator — proactive about problems, clear about status, and always moving toward a better-run lab.

YOUR HOME LAB STACK:
- 🌐 Network & Security: UniFi (UDM/UDM Pro) — internet, WiFi clients, cameras (Protect)
- 🖥️  Server: Ubuntu Linux with Nvidia GPU — SSH access for real-time resource monitoring
- 🎬 Media: Plex Media Server — libraries, streams, recently added
- 🏠 Automation: Home Assistant — entities, automations, alerts
- 🤖 Local AI: Ollama — locally-hosted LLMs, model management
- 🔒  DNS: CoreDNS — local DNS resolver, custom A records, upstream forwarding
- 🐋 Containers: Portainer — Docker container lifecycle management
- 📋 Dashboard: Homepage — service status aggregation

OPERATING PRINCIPLES:
1. Always check relevant service health before making recommendations
2. Diagnose issues methodically — gather data, identify root cause, suggest fix
3. When containers are unhealthy or services are down, surface actionable next steps
4. Monitor trends — flag if GPU temp is climbing, if a container keeps restarting, etc.
5. Suggest automation improvements in Home Assistant when relevant
6. Be concise and technical. Lead with status, then detail.

Today's date: {today}
"""


class HomeLabAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.model = Config.CLAUDE_MODEL
        self.system_pipeline = SystemPipeline()
        self.unifi = UniFiPipeline()
        self.plex = PlexPipeline()
        self.ha = HomeAssistantPipeline()
        self.ollama = OllamaPipeline()
        self.dns = DNSPipeline()
        self.portainer = PortainerPipeline()
        self.homepage = HomepagePipeline()

    # ── Public ────────────────────────────────────────────────────────────────

    def chat(self, message: str, history: list[dict] = None) -> str:
        if history is None:
            history = []

        messages = list(history) + [{"role": "user", "content": message}]
        system = SYSTEM_PROMPT.format(today=datetime.now().strftime("%A, %B %d, %Y"))

        while True:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                tools=self._get_tools(),
                messages=messages,
            )

            if resp.stop_reason == "end_turn":
                return self._extract_text(resp)

            if resp.stop_reason == "tool_use":
                tool_results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        result = self._execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        })
                messages.append({"role": "assistant", "content": resp.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                return self._extract_text(resp)

    # ── Tool Definitions ──────────────────────────────────────────────────────

    def _get_tools(self) -> list[dict]:
        return [
            # System — multi-machine
            {
                "name": "get_system_health",
                "description": (
                    "Get real-time system health by SSHing into one or all monitored machines. "
                    "Mac (Docker host): runs macOS top + vm_stat + df — no GPU stats. "
                    "Ubuntu server: runs Linux top + df + nvidia-smi for Nvidia GPU. "
                    "Use machine='all' to poll both simultaneously."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "machine": {
                            "type": "string",
                            "enum": ["all", "local", "remote"],
                            "description": "'all' polls every configured machine (default), 'local' polls the Mac, 'remote' polls the Ubuntu server.",
                            "default": "all",
                        },
                    },
                },
            },
            {
                "name": "get_system_history",
                "description": "Get historical system health snapshots from the database. Filter by machine_name to scope to one host.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of snapshots to return", "default": 24},
                        "machine_name": {"type": "string", "description": "Filter to a specific machine by name (e.g. 'Mac', 'Ubuntu Server')"},
                    },
                },
            },
            # UniFi Network
            {
                "name": "get_unifi_network",
                "description": "Get UniFi network stats: WAN IP, ISP, throughput, connected clients (WiFi + wired), uptime.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_unifi_clients",
                "description": "Get list of all connected clients on the UniFi network with IP, MAC, signal strength.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_unifi_devices",
                "description": "Get UniFi network devices (APs, switches, router) with CPU/mem and version info.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_unifi_alerts",
                "description": "Get active (unarchived) UniFi network alerts.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_unifi_protect",
                "description": "Get UniFi Protect security camera summary — camera count, recording status, connectivity.",
                "input_schema": {"type": "object", "properties": {}},
            },
            # Plex
            {
                "name": "get_plex_summary",
                "description": "Get Plex media server summary: active streams, library counts, now playing.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_plex_recent",
                "description": "Get recently added Plex media items.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 10},
                    },
                },
            },
            # Home Assistant
            {
                "name": "get_homeassistant_summary",
                "description": "Get Home Assistant summary: entity count, automations on, alerts and unavailable entities.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_homeassistant_entities",
                "description": "Get Home Assistant entities, optionally filtered by domain (light, switch, sensor, automation, etc.).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string", "description": "Entity domain to filter by (e.g. 'light', 'sensor')"},
                    },
                },
            },
            {
                "name": "call_homeassistant_service",
                "description": "Call a Home Assistant service to control a device or automation.",
                "input_schema": {
                    "type": "object",
                    "required": ["domain", "service", "entity_id"],
                    "properties": {
                        "domain": {"type": "string", "description": "Service domain (e.g. 'light', 'switch', 'automation')"},
                        "service": {"type": "string", "description": "Service name (e.g. 'turn_on', 'turn_off', 'toggle')"},
                        "entity_id": {"type": "string"},
                        "extra": {"type": "object", "description": "Additional service parameters (e.g. brightness, color_temp)"},
                    },
                },
            },
            # Ollama
            {
                "name": "get_ollama_models",
                "description": "Get list of all installed Ollama models with size and quantization details.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_ollama_running",
                "description": "Get currently running/loaded Ollama models.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "ollama_generate",
                "description": "Send a prompt to an Ollama model and get a response. Useful for testing local models.",
                "input_schema": {
                    "type": "object",
                    "required": ["model", "prompt"],
                    "properties": {
                        "model": {"type": "string", "description": "Ollama model name (e.g. 'llama3.2', 'mistral')"},
                        "prompt": {"type": "string"},
                    },
                },
            },
            # CoreDNS
            {
                "name": "get_dns_summary",
                "description": "Get CoreDNS local DNS server status: online/offline, custom record count, upstream resolvers.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_dns_records",
                "description": "List all custom local DNS A records (hostname → IP mappings) managed by CoreDNS.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "dns_add_record",
                "description": "Add a new custom local DNS A record so a hostname resolves to a specific IP on the LAN.",
                "input_schema": {
                    "type": "object",
                    "required": ["ip", "domain"],
                    "properties": {
                        "ip":     {"type": "string", "description": "IPv4 address (e.g. '192.168.1.50')"},
                        "domain": {"type": "string", "description": "Hostname (e.g. 'myserver.local')"},
                    },
                },
            },
            {
                "name": "dns_delete_record",
                "description": "Remove a custom local DNS A record from CoreDNS.",
                "input_schema": {
                    "type": "object",
                    "required": ["ip", "domain"],
                    "properties": {
                        "ip":     {"type": "string", "description": "IPv4 address of the record to remove"},
                        "domain": {"type": "string", "description": "Hostname of the record to remove"},
                    },
                },
            },
            # Portainer
            {
                "name": "get_portainer_summary",
                "description": "Get Portainer container summary: running, stopped, unhealthy counts and full container list.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "endpoint_id": {"type": "integer", "default": 1},
                    },
                },
            },
            {
                "name": "portainer_container_action",
                "description": "Start, stop, restart, pause, or unpause a Docker container via Portainer.",
                "input_schema": {
                    "type": "object",
                    "required": ["container_id", "action"],
                    "properties": {
                        "endpoint_id": {"type": "integer", "default": 1},
                        "container_id": {"type": "string", "description": "Container ID or name"},
                        "action": {"type": "string", "enum": ["start", "stop", "restart", "pause", "unpause"]},
                    },
                },
            },
            {
                "name": "get_portainer_stacks",
                "description": "Get all Docker stacks managed by Portainer.",
                "input_schema": {"type": "object", "properties": {}},
            },
            # Homepage
            {
                "name": "get_homepage_status",
                "description": "Get the status of the Homepage dashboard service.",
                "input_schema": {"type": "object", "properties": {}},
            },
            # Full status sweep
            {
                "name": "get_full_homelab_status",
                "description": "Run a comprehensive status check of ALL home lab services at once. Use when asked for an overview or health check.",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]

    # ── Tool Execution ────────────────────────────────────────────────────────

    def _execute_tool(self, name: str, inputs: dict) -> dict:
        logger.info("HomeLabAgent tool: %s(%s)", name, inputs)
        try:
            # System — multi-machine
            if name == "get_system_health":
                machine = inputs.get("machine", "all")
                result = self.system_pipeline.get_system_health(machine=machine)
                # Normalise: always return as list for consistent agent reasoning
                if isinstance(result, dict):
                    return {"machines": [result]}
                return {"machines": result}
            elif name == "get_system_history":
                return {"history": self.system_pipeline.get_history(
                    limit=inputs.get("limit", 24),
                    machine_name=inputs.get("machine_name"),
                )}
            # UniFi
            elif name == "get_unifi_network":
                return self.unifi.get_network_stats()
            elif name == "get_unifi_clients":
                return {"clients": self.unifi.get_clients()}
            elif name == "get_unifi_devices":
                return {"devices": self.unifi.get_devices()}
            elif name == "get_unifi_alerts":
                return {"alerts": self.unifi.get_alerts()}
            elif name == "get_unifi_protect":
                return self.unifi.get_protect_summary()
            # Plex
            elif name == "get_plex_summary":
                return self.plex.get_summary()
            elif name == "get_plex_recent":
                return {"recent": self.plex.get_recent(limit=inputs.get("limit", 10))}
            # Home Assistant
            elif name == "get_homeassistant_summary":
                return self.ha.get_summary()
            elif name == "get_homeassistant_entities":
                return {"entities": self.ha.get_entities(domain=inputs.get("domain"))}
            elif name == "call_homeassistant_service":
                return self.ha.call_service(
                    domain=inputs["domain"],
                    service=inputs["service"],
                    entity_id=inputs["entity_id"],
                    extra=inputs.get("extra"),
                )
            # Ollama
            elif name == "get_ollama_models":
                return self.ollama.get_summary()
            elif name == "get_ollama_running":
                return {"running": self.ollama.get_running()}
            elif name == "ollama_generate":
                response = self.ollama.generate(inputs["model"], inputs["prompt"])
                return {"response": response}
            # CoreDNS
            elif name == "get_dns_summary":
                return self.dns.get_summary()
            elif name == "get_dns_records":
                return {"records": self.dns.get_records()}
            elif name == "dns_add_record":
                return self.dns.add_record(inputs["ip"], inputs["domain"])
            elif name == "dns_delete_record":
                return self.dns.delete_record(inputs["ip"], inputs["domain"])
            # Portainer
            elif name == "get_portainer_summary":
                return self.portainer.get_summary(endpoint_id=inputs.get("endpoint_id", 1))
            elif name == "portainer_container_action":
                return self.portainer.container_action(
                    endpoint_id=inputs.get("endpoint_id", 1),
                    container_id=inputs["container_id"],
                    action=inputs["action"],
                )
            elif name == "get_portainer_stacks":
                return {"stacks": self.portainer.get_stacks()}
            # Homepage
            elif name == "get_homepage_status":
                return self.homepage.get_status()
            # Full sweep
            elif name == "get_full_homelab_status":
                return self._full_status_sweep()
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.error("HomeLabAgent tool %s error: %s", name, e)
            return {"error": str(e)}

    def _full_status_sweep(self) -> dict:
        """Run all service checks concurrently (simple sequential for now)."""
        results = {}
        services = [
            ("system", lambda: self.system_pipeline.get_all_machines()),
            ("unifi_network", lambda: self.unifi.get_network_stats()),
            ("plex", lambda: self.plex.get_summary()),
            ("home_assistant", lambda: self.ha.get_summary()),
            ("ollama", lambda: self.ollama.get_summary()),
            ("dns", lambda: self.dns.get_summary()),
            ("portainer", lambda: self.portainer.get_summary()),
            ("homepage", lambda: self.homepage.get_status()),
        ]
        for service_name, fn in services:
            try:
                results[service_name] = fn()
            except Exception as e:
                results[service_name] = {"error": str(e)}
        return results

    def _extract_text(self, resp) -> str:
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text
        return ""
