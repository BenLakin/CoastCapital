"""
CoastCapital HomeLab — Flask application factory + all routes.
"""
import os
import uuid
from datetime import datetime
from functools import wraps

from flask import Flask, g, jsonify, request, render_template, Response

from app.config import Config
from app.db import init_db, get_conn
from app.utils.logging_config import get_logger
from app.utils.metrics import init_metrics

logger = get_logger(__name__)


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = Config.SECRET_KEY
    init_metrics(app, module="homelab")

    # X-Request-ID header
    @app.after_request
    def _add_request_id(response):
        rid = request.headers.get("X-Request-ID", uuid.uuid4().hex[:8])
        response.headers["X-Request-ID"] = rid
        return response

    # Bootstrap DB on startup
    try:
        init_db()
    except Exception as e:
        logger.error("DB init failed: %s", e)

    # ── Auth middleware ───────────────────────────────────────────────────────

    def require_api_key(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            key = request.headers.get("X-API-Key") or request.args.get("api_key")
            if Config.API_KEY and key != Config.API_KEY:
                return jsonify({"success": False, "error": "Unauthorized"}), 401
            return f(*args, **kwargs)
        return decorated

    # ── Lazy pipeline singletons ──────────────────────────────────────────────

    def get_system():
        from app.pipelines.system_pipeline import SystemPipeline
        return SystemPipeline()

    def get_unifi():
        from app.pipelines.unifi_pipeline import UniFiPipeline
        return UniFiPipeline()

    def get_plex():
        from app.pipelines.plex_pipeline import PlexPipeline
        return PlexPipeline()

    def get_ha():
        from app.pipelines.homeassistant_pipeline import HomeAssistantPipeline
        return HomeAssistantPipeline()

    def get_ollama():
        from app.pipelines.ollama_pipeline import OllamaPipeline
        return OllamaPipeline()

    def get_dns():
        from app.pipelines.dns_pipeline import DNSPipeline
        return DNSPipeline()

    def get_portainer():
        from app.pipelines.portainer_pipeline import PortainerPipeline
        return PortainerPipeline()

    def get_homepage():
        from app.pipelines.homepage_pipeline import HomepagePipeline
        return HomepagePipeline()

    def get_agent():
        from app.agents.homelab_agent import HomeLabAgent
        return HomeLabAgent()

    # ── Web UI ────────────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return render_template("dashboard.html")

    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html")

    # ── Health check ──────────────────────────────────────────────────────────

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "service": "coastcapital-homelab", "ts": datetime.now().isoformat()})

    # ── n8n Pipeline Endpoints ────────────────────────────────────────────────
    # All require X-API-Key header

    @app.route("/api/pipeline/system", methods=["GET", "POST"])
    @require_api_key
    def pipeline_system():
        # ?machine=all|local|remote  (default: all)
        machine = request.args.get("machine", "all")
        data = get_system().get_system_health(machine=machine)
        return jsonify(data)

    @app.route("/api/pipeline/system/local", methods=["GET", "POST"])
    @require_api_key
    def pipeline_system_local():
        return jsonify(get_system().get_local_health())

    @app.route("/api/pipeline/system/remote", methods=["GET", "POST"])
    @require_api_key
    def pipeline_system_remote():
        return jsonify(get_system().get_remote_health())

    @app.route("/api/pipeline/system/history", methods=["GET"])
    @require_api_key
    def pipeline_system_history():
        limit = int(request.args.get("limit", 24))
        machine_name = request.args.get("machine_name")  # optional filter
        return jsonify({"history": get_system().get_history(limit=limit, machine_name=machine_name)})

    @app.route("/api/pipeline/unifi/network", methods=["GET", "POST"])
    @require_api_key
    def pipeline_unifi_network():
        return jsonify(get_unifi().get_network_stats())

    @app.route("/api/pipeline/unifi/clients", methods=["GET"])
    @require_api_key
    def pipeline_unifi_clients():
        return jsonify({"clients": get_unifi().get_clients()})

    @app.route("/api/pipeline/unifi/devices", methods=["GET"])
    @require_api_key
    def pipeline_unifi_devices():
        return jsonify({"devices": get_unifi().get_devices()})

    @app.route("/api/pipeline/unifi/alerts", methods=["GET"])
    @require_api_key
    def pipeline_unifi_alerts():
        return jsonify({"alerts": get_unifi().get_alerts()})

    @app.route("/api/pipeline/unifi/protect", methods=["GET"])
    @require_api_key
    def pipeline_unifi_protect():
        return jsonify(get_unifi().get_protect_summary())

    @app.route("/api/pipeline/unifi/protect/snapshot/<camera_id>", methods=["GET"])
    @require_api_key
    def pipeline_protect_snapshot(camera_id):
        """Proxy a JPEG snapshot from UniFi Protect so the browser avoids CORS/auth."""
        try:
            image_bytes = get_unifi().get_camera_snapshot(camera_id)
            return Response(image_bytes, mimetype="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        except Exception as e:
            logger.error("Protect snapshot error [%s]: %s", camera_id, e)
            return jsonify({"success": False, "error": str(e)}), 502

    @app.route("/api/pipeline/plex", methods=["GET", "POST"])
    @require_api_key
    def pipeline_plex():
        return jsonify(get_plex().get_summary())

    @app.route("/api/pipeline/plex/recent", methods=["GET"])
    @require_api_key
    def pipeline_plex_recent():
        limit = int(request.args.get("limit", 10))
        return jsonify({"recent": get_plex().get_recent(limit=limit)})

    @app.route("/api/pipeline/homeassistant", methods=["GET", "POST"])
    @require_api_key
    def pipeline_homeassistant():
        return jsonify(get_ha().get_summary())

    @app.route("/api/pipeline/homeassistant/entities", methods=["GET"])
    @require_api_key
    def pipeline_ha_entities():
        domain = request.args.get("domain")
        return jsonify({"entities": get_ha().get_entities(domain=domain)})

    @app.route("/api/pipeline/homeassistant/service", methods=["POST"])
    @require_api_key
    def pipeline_ha_service():
        body = request.get_json() or {}
        result = get_ha().call_service(
            domain=body.get("domain", ""),
            service=body.get("service", ""),
            entity_id=body.get("entity_id", ""),
            extra=body.get("extra"),
        )
        return jsonify(result)

    @app.route("/api/pipeline/ollama", methods=["GET", "POST"])
    @require_api_key
    def pipeline_ollama():
        return jsonify(get_ollama().get_summary())

    @app.route("/api/pipeline/ollama/running", methods=["GET"])
    @require_api_key
    def pipeline_ollama_running():
        return jsonify({"running": get_ollama().get_running()})

    @app.route("/api/pipeline/ollama/generate", methods=["POST"])
    @require_api_key
    def pipeline_ollama_generate():
        body = request.get_json() or {}
        response = get_ollama().generate(body.get("model", ""), body.get("prompt", ""))
        return jsonify({"response": response})

    @app.route("/api/pipeline/dns", methods=["GET", "POST"])
    @require_api_key
    def pipeline_dns():
        return jsonify(get_dns().get_summary())

    @app.route("/api/pipeline/dns/records", methods=["GET"])
    @require_api_key
    def pipeline_dns_records():
        return jsonify({"records": get_dns().get_records()})

    @app.route("/api/pipeline/dns/add", methods=["POST"])
    @require_api_key
    def pipeline_dns_add():
        body   = request.get_json() or {}
        ip     = body.get("ip", "").strip()
        domain = body.get("domain", "").strip()
        if not ip or not domain:
            return jsonify({"success": False, "error": "ip and domain are required"}), 400
        return jsonify(get_dns().add_record(ip, domain))

    @app.route("/api/pipeline/dns/delete", methods=["POST"])
    @require_api_key
    def pipeline_dns_delete():
        body   = request.get_json() or {}
        ip     = body.get("ip", "").strip()
        domain = body.get("domain", "").strip()
        if not ip or not domain:
            return jsonify({"success": False, "error": "ip and domain are required"}), 400
        return jsonify(get_dns().delete_record(ip, domain))

    @app.route("/api/pipeline/portainer", methods=["GET", "POST"])
    @require_api_key
    def pipeline_portainer():
        endpoint_id = int(request.args.get("endpoint_id", 1))
        return jsonify(get_portainer().get_summary(endpoint_id=endpoint_id))

    @app.route("/api/pipeline/portainer/container/<container_id>/<action>", methods=["POST"])
    @require_api_key
    def pipeline_portainer_action(container_id, action):
        endpoint_id = int(request.args.get("endpoint_id", 1))
        result = get_portainer().container_action(endpoint_id, container_id, action)
        return jsonify(result)

    @app.route("/api/pipeline/portainer/stacks", methods=["GET"])
    @require_api_key
    def pipeline_portainer_stacks():
        return jsonify({"stacks": get_portainer().get_stacks()})

    @app.route("/api/pipeline/homepage", methods=["GET"])
    @require_api_key
    def pipeline_homepage():
        return jsonify(get_homepage().get_status())

    @app.route("/api/pipeline/full-status", methods=["GET", "POST"])
    @require_api_key
    def pipeline_full_status():
        """All-services sweep — used by n8n for dashboard updates."""
        results = {}
        checks = [
            ("system", lambda: get_system().get_system_health()),
            ("unifi_network", lambda: get_unifi().get_network_stats()),
            ("plex", lambda: get_plex().get_summary()),
            ("home_assistant", lambda: get_ha().get_summary()),
            ("ollama", lambda: get_ollama().get_summary()),
            ("dns", lambda: get_dns().get_summary()),
            ("portainer", lambda: get_portainer().get_summary()),
            ("homepage", lambda: get_homepage().get_status()),
        ]
        for name, fn in checks:
            try:
                results[name] = fn()
            except Exception as e:
                results[name] = {"error": str(e)}
        return jsonify({"status": results, "ts": datetime.now().isoformat()})

    # ── HomeLabAgent chat ─────────────────────────────────────────────────────

    @app.route("/api/agent/chat", methods=["POST"])
    @require_api_key
    def agent_chat():
        body = request.get_json() or {}
        message = body.get("message", "").strip()
        history = body.get("history", [])
        if not message:
            return jsonify({"success": False, "error": "message required"}), 400
        try:
            agent = get_agent()
            reply = agent.chat(message, history=history)
            return jsonify({"reply": reply})
        except Exception as e:
            logger.error("Agent chat error: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    # ── Events log ───────────────────────────────────────────────────────────

    @app.route("/api/events", methods=["GET"])
    @require_api_key
    def get_events():
        limit = int(request.args.get("limit", 50))
        source = request.args.get("source")
        severity = request.args.get("severity")
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            query = "SELECT * FROM homelab_events WHERE 1=1"
            params = []
            if source:
                query += " AND source = %s"
                params.append(source)
            if severity:
                query += " AND severity = %s"
                params.append(severity)
            query += " ORDER BY event_at DESC LIMIT %s"
            params.append(limit)
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            for r in rows:
                if r.get("event_at"):
                    r["event_at"] = r["event_at"].isoformat()
            return jsonify({"events": rows})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    return app
