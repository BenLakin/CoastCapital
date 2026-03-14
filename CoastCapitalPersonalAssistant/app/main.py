"""
CoastCapital Personal Assistant — Flask Application
n8n-callable pipeline endpoints + personal web dashboard.
"""
import logging
import os
import time
import traceback
import uuid
from functools import wraps

from flask import Flask, g, request, jsonify, render_template
from flask_cors import CORS

from app.config import Config
from app.db import init_db, get_conn  # noqa: E402 — imported after app init
from app.logging_config import setup_logging
from app.utils.metrics import log_pageview, log_error, metrics_response, ensure_table

setup_logging(
    log_dir=os.environ.get("LOG_DIR", "logs"),
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
CORS(app, origins=[
    "http://localhost:5100",
    "http://127.0.0.1:5100",
    "http://macmini.local:5100",
])


@app.context_processor
def inject_globals():
    return {"config": Config, "request": request}


# ── Request logging ───────────────────────────────────────────────────────────

@app.before_request
def _start_request():
    g.request_id = uuid.uuid4().hex[:8]
    g.start_time = time.monotonic()


@app.after_request
def _log_request(response):
    elapsed_ms = (time.monotonic() - g.get("start_time", time.monotonic())) * 1000
    logger.info(
        "[%s] %s %s → %d (%.0fms)",
        g.get("request_id", "-"),
        request.method,
        request.path,
        response.status_code,
        elapsed_ms,
    )
    response.headers["X-Request-ID"] = g.get("request_id", "-")
    log_pageview(module="assistant", path=request.path, method=request.method,
                 status_code=response.status_code, duration_ms=int(elapsed_ms))
    return response


# ── Auth decorator ────────────────────────────────────────────────────────────

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if key != Config.API_KEY:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def pipeline_handler(f):
    """Wraps a pipeline function with error handling and JSON response."""
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            logger.error("Pipeline error in %s: %s", f.__name__, traceback.format_exc())
            return jsonify({"success": False, "error": str(e)}), 500
    return decorated


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    from datetime import datetime
    return jsonify({"status": "ok", "service": "coastcapital-assistant", "ts": datetime.now().isoformat()})


@app.route("/metrics")
def prometheus_metrics():
    return metrics_response()


# Ensure web_analytics table exists on startup
ensure_table()


# ── Pipeline: Email Summary ───────────────────────────────────────────────────

@app.route("/api/pipeline/email-summary", methods=["GET", "POST"])
@require_api_key
@pipeline_handler
def email_summary():
    """Fetch recent iCloud emails and return AI summaries."""
    from app.pipelines.email_pipeline import EmailPipeline
    body = request.get_json(silent=True) or {}
    days = body.get("days", 7)
    folder = body.get("folder", "INBOX")
    limit = body.get("limit", 30)
    return EmailPipeline().fetch_and_summarize(days=days, folder=folder, limit=limit)


# ── Pipeline: News Summary ────────────────────────────────────────────────────

@app.route("/api/pipeline/news-summary", methods=["GET", "POST"])
@require_api_key
@pipeline_handler
def news_summary():
    """Fetch world/tech/AI/B2B news and return summaries."""
    from app.pipelines.news_pipeline import NewsPipeline
    body = request.get_json(silent=True) or {}
    categories = body.get("categories", ["world", "technology", "ai", "b2b"])
    return NewsPipeline().fetch_and_summarize(categories=categories)


# ── Pipeline: Calendar ────────────────────────────────────────────────────────

@app.route("/api/pipeline/calendar", methods=["GET", "POST"])
@require_api_key
@pipeline_handler
def calendar_events():
    """Return upcoming calendar events from iCloud."""
    from app.pipelines.calendar_pipeline import CalendarPipeline
    body = request.get_json(silent=True) or {}
    days_ahead = body.get("days_ahead", 14)
    return CalendarPipeline().get_upcoming_events(days_ahead=days_ahead)


# ── Pipeline: Communications Plan ─────────────────────────────────────────────

@app.route("/api/pipeline/comms-plan", methods=["POST"])
@require_api_key
@pipeline_handler
def comms_plan():
    """Build a personalized communication action plan."""
    from app.pipelines.communications_pipeline import CommunicationsPipeline
    body = request.get_json(silent=True) or {}
    force_refresh = body.get("force_refresh", False)
    return CommunicationsPipeline().build_plan(force_refresh=force_refresh)


# ── Pipeline: Deliveries & Events ─────────────────────────────────────────────

@app.route("/api/pipeline/deliveries", methods=["GET", "POST"])
@require_api_key
@pipeline_handler
def deliveries():
    """Scan email for delivery notifications and upcoming personal events."""
    from app.pipelines.deliveries_pipeline import DeliveriesPipeline
    return DeliveriesPipeline().fetch_all()


# ── Pipeline: Archive Emails ──────────────────────────────────────────────────

@app.route("/api/pipeline/archive-emails", methods=["POST"])
@require_api_key
@pipeline_handler
def archive_emails():
    """Apply archiving rules and suggest new rules based on patterns."""
    from app.pipelines.archive_pipeline import ArchivePipeline
    body = request.get_json(silent=True) or {}
    dry_run = body.get("dry_run", True)
    learn = body.get("learn_new_rules", True)
    return ArchivePipeline().run(dry_run=dry_run, learn_new_rules=learn)


# ── Pipeline: Dashboard Data ──────────────────────────────────────────────────

@app.route("/api/pipeline/reminders", methods=["GET", "POST"])
@require_api_key
@pipeline_handler
def get_reminders():
    """Fetch iCloud Reminders (VTODO items)."""
    from app.pipelines.reminders_pipeline import RemindersPipeline
    body = request.get_json(silent=True) or {}
    include_completed = body.get("include_completed", False)
    return RemindersPipeline().get_reminders(include_completed=include_completed)


@app.route("/api/pipeline/reminders/add", methods=["POST"])
@require_api_key
@pipeline_handler
def add_reminder():
    """Create a new iCloud Reminder."""
    from app.pipelines.reminders_pipeline import RemindersPipeline
    body = request.get_json(silent=True) or {}
    if not body.get("title"):
        raise ValueError("title is required")
    return RemindersPipeline().add_reminder(
        title=body["title"],
        notes=body.get("notes", ""),
        due_date=body.get("due_date", ""),
        priority=body.get("priority", 5),
        list_name=body.get("list_name", "Reminders"),
    )


@app.route("/api/pipeline/dashboard-data", methods=["GET"])
@require_api_key
@pipeline_handler
def dashboard_data():
    """Return aggregated data for the dashboard from DB cache."""
    return _get_dashboard_data()


# ── Pipeline: Weather ─────────────────────────────────────────────────────

@app.route("/api/pipeline/weather", methods=["GET"])
@require_api_key
@pipeline_handler
def weather():
    """Return current conditions and 5-day forecast from Open-Meteo."""
    from app.pipelines.weather_pipeline import WeatherPipeline
    zip_code = request.args.get("zip")
    return WeatherPipeline().fetch(zip_code=zip_code)


# ── Pipeline: Morning Briefing ────────────────────────────────────────────────

@app.route("/api/pipeline/morning-briefing", methods=["GET", "POST"])
@require_api_key
@pipeline_handler
def morning_briefing():
    from app.pipelines.morning_briefing_pipeline import MorningBriefingPipeline
    body = request.get_json(silent=True) or {}
    return MorningBriefingPipeline().generate(
        send_email=body.get("send_email", False),
        city=body.get("city", ""),
    )


# ── Pipeline: Follow-up Tracker ───────────────────────────────────────────────

@app.route("/api/pipeline/followup", methods=["GET", "POST"])
@require_api_key
@pipeline_handler
def followup():
    from app.pipelines.followup_pipeline import FollowupPipeline
    body = request.get_json(silent=True) or {}
    return FollowupPipeline().scan(
        wait_days=body.get("wait_days", 3),
        limit=body.get("limit", 100),
    )

@app.route("/api/pipeline/followup/dismiss/<int:followup_id>", methods=["POST"])
@require_api_key
def dismiss_followup(followup_id):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE followup_tracker SET status='dismissed', dismissed_at=NOW() WHERE id=%s",
            (followup_id,),
        )
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Pipeline: Travel ──────────────────────────────────────────────────────────

@app.route("/api/pipeline/travel", methods=["GET", "POST"])
@require_api_key
@pipeline_handler
def travel():
    from app.pipelines.travel_pipeline import TravelPipeline
    body = request.get_json(silent=True) or {}
    if request.method == "GET":
        return TravelPipeline().get_upcoming()
    return TravelPipeline().scan(days=body.get("days", 60))

@app.route("/api/pipeline/travel/<int:trip_id>/status", methods=["POST"])
@require_api_key
def update_travel_status(trip_id):
    body = request.get_json(silent=True) or {}
    status = body.get("status", "upcoming")
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE travel_itineraries SET status=%s WHERE id=%s", (status, trip_id))
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Pipeline: Birthdays ───────────────────────────────────────────────────────

@app.route("/api/pipeline/birthdays", methods=["GET", "POST"])
@require_api_key
@pipeline_handler
def birthdays():
    from app.pipelines.birthday_pipeline import BirthdayPipeline
    return BirthdayPipeline().get_upcoming_birthdays()


# ── Relationship API ──────────────────────────────────────────────────────────

@app.route("/api/relationship", methods=["POST"])
@require_api_key
def create_relationship():
    from app.pipelines.birthday_pipeline import BirthdayPipeline
    body = request.get_json(silent=True) or {}
    if not body.get("name"):
        return jsonify({"error": "name is required"}), 400
    result = BirthdayPipeline().create_relationship(
        name=body["name"],
        email=body.get("email", ""),
        birthday=body.get("birthday", ""),
        relationship_type=body.get("relationship_type", "family"),
        notes=body.get("notes", ""),
        is_family=body.get("is_family", False),
    )
    return jsonify(result)

@app.route("/api/relationship/<int:rel_id>", methods=["GET"])
@require_api_key
def get_relationship(rel_id):
    from app.pipelines.birthday_pipeline import BirthdayPipeline
    return jsonify(BirthdayPipeline().get_full_profile(rel_id))

@app.route("/api/relationship/<int:rel_id>/preferences", methods=["POST"])
@require_api_key
def log_preference(rel_id):
    from app.pipelines.birthday_pipeline import BirthdayPipeline
    body = request.get_json(silent=True) or {}
    if not body.get("category") or not body.get("preference"):
        return jsonify({"error": "category and preference required"}), 400
    result = BirthdayPipeline().log_preference(
        relationship_id=rel_id,
        category=body["category"],
        preference=body["preference"],
        source=body.get("source", "manual"),
    )
    return jsonify(result)

@app.route("/api/relationship/<int:rel_id>/gifts", methods=["POST"])
@require_api_key
def log_gift(rel_id):
    from app.pipelines.birthday_pipeline import BirthdayPipeline
    body = request.get_json(silent=True) or {}
    result = BirthdayPipeline().log_gift(
        relationship_id=rel_id,
        occasion=body.get("occasion", "birthday"),
        description=body.get("gift_description", ""),
        status=body.get("status", "given"),
        price=body.get("price"),
        reaction=body.get("reaction", ""),
        purchase_url=body.get("purchase_url", ""),
    )
    return jsonify(result)

@app.route("/api/relationship/<int:rel_id>/interactions", methods=["POST"])
@require_api_key
def log_interaction(rel_id):
    from app.pipelines.birthday_pipeline import BirthdayPipeline
    body = request.get_json(silent=True) or {}
    result = BirthdayPipeline().log_interaction(
        relationship_id=rel_id,
        interaction_type=body.get("type", "note"),
        summary=body.get("summary", ""),
        sentiment=body.get("sentiment", "neutral"),
    )
    return jsonify(result)

@app.route("/api/relationship/<int:rel_id>/gift-suggestions", methods=["POST"])
@require_api_key
@pipeline_handler
def gift_suggestions(rel_id):
    from app.pipelines.birthday_pipeline import BirthdayPipeline
    body = request.get_json(silent=True) or {}
    return BirthdayPipeline().get_gift_suggestions(
        relationship_id=rel_id,
        budget=body.get("budget", "any"),
    )


# ── Relationship Web Page ─────────────────────────────────────────────────────

@app.route("/relationship/<int:rel_id>")
def relationship_profile(rel_id):
    from app.pipelines.birthday_pipeline import BirthdayPipeline, PREFERENCE_CATEGORIES
    profile = BirthdayPipeline().get_full_profile(rel_id)
    return render_template(
        "relationship_profile.html",
        profile=profile,
        categories=PREFERENCE_CATEGORIES,
        owner=Config.OWNER_NAME,
    )

@app.route("/relationships")
def relationships_list():
    try:
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, name, email, birthday, relationship_type, is_family, last_contacted "
            "FROM relationships ORDER BY is_family DESC, name ASC"
        )
        people = cur.fetchall()
        cur.close()
        conn.close()
    except Exception:
        people = []
    return render_template("relationships_list.html", people=people, owner=Config.OWNER_NAME)


# ── Agent: AssistantAgent chat ────────────────────────────────────────────────

@app.route("/api/agent/chat", methods=["POST"])
@require_api_key
def agent_chat():
    """Send a message to AssistantAgent and receive a response."""
    from app.agents.assistant_agent import AssistantAgent
    body = request.get_json(silent=True) or {}
    message = body.get("message", "")
    conversation_history = body.get("history", [])
    if not message:
        return jsonify({"error": "No message provided"}), 400
    try:
        agent = AssistantAgent()
        response = agent.chat(message, history=conversation_history)
        return jsonify({"success": True, "response": response})
    except Exception as e:
        logger.error("Agent error: %s", traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ── Send Email (1-click from dashboard) ──────────────────────────────────────

@app.route("/api/send-email", methods=["POST"])
@require_api_key
def send_email():
    """Send an email via iCloud SMTP. Used by 1-click action items."""
    from app.pipelines.email_pipeline import EmailPipeline
    body = request.get_json(silent=True) or {}
    required = ["to", "subject", "body"]
    for field in required:
        if not body.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400
    try:
        EmailPipeline().send_email(
            to=body["to"],
            subject=body["subject"],
            body=body["body"],
            cc=body.get("cc", ""),
        )
        # Mark action item as done if action_id provided
        action_id = body.get("action_id")
        if action_id:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE action_items SET status='sent' WHERE id=%s",
                    (action_id,),
                )
                cur.close()
                conn.close()
            except Exception:
                pass
        return jsonify({"success": True, "message": "Email sent"})
    except Exception as e:
        logger.error("Send email error: %s", traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ── Web Pages ─────────────────────────────────────────────────────────────────

@app.route("/")
@app.route("/dashboard")
def dashboard():
    data = _get_dashboard_data()
    return render_template("dashboard.html", data=data, owner=Config.OWNER_NAME)


@app.route("/communications")
def communications():
    try:
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM action_items WHERE status='pending' ORDER BY priority, created_at DESC LIMIT 50"
        )
        items = cur.fetchall()
        cur.close()
        conn.close()
    except Exception:
        items = []
    return render_template("communications.html", items=items, owner=Config.OWNER_NAME)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_dashboard_data() -> dict:
    result = {
        "emails": [], "news": [], "action_items": [], "deliveries": [],
        "followups": [], "travel": [], "birthdays": [],
        "morning_briefing": None, "activity_log": [],
    }
    try:
        conn = get_conn()
        cur = conn.cursor(dictionary=True)

        # Email metadata + AI summaries only — bodies never stored here
        cur.execute(
            "SELECT from_addr, subject, date_sent, summary, is_family "
            "FROM email_cache ORDER BY fetched_at DESC LIMIT 20"
        )
        result["emails"] = cur.fetchall()

        cur.execute(
            "SELECT category, title, source, url, summary "
            "FROM news_cache ORDER BY fetched_at DESC LIMIT 30"
        )
        result["news"] = cur.fetchall()

        cur.execute(
            "SELECT id, priority, title, detail, action_type, recipient, "
            "email_subject, email_body, status "
            "FROM action_items WHERE status='pending' ORDER BY priority, created_at DESC LIMIT 20"
        )
        result["action_items"] = cur.fetchall()

        cur.execute(
            "SELECT carrier, tracking_num, description, status, expected_date "
            "FROM deliveries WHERE status != 'Delivered' ORDER BY detected_at DESC LIMIT 10"
        )
        result["deliveries"] = cur.fetchall()

        cur.execute(
            "SELECT id, to_addr, subject, sent_at, days_waiting "
            "FROM followup_tracker WHERE status='waiting' "
            "ORDER BY days_waiting DESC LIMIT 10"
        )
        result["followups"] = cur.fetchall()

        cur.execute(
            "SELECT id, trip_name, destination, depart_date, return_date, "
            "carrier, booking_type, confirmation_num, status "
            "FROM travel_itineraries WHERE depart_date >= CURDATE() "
            "AND status='upcoming' ORDER BY depart_date ASC LIMIT 5"
        )
        result["travel"] = cur.fetchall()

        cur.execute(
            """SELECT name, birthday, email, id,
                      DATEDIFF(
                        DATE(CONCAT(YEAR(CURDATE()),'-',
                             LPAD(MONTH(birthday),2,'0'),'-',
                             LPAD(DAY(birthday),2,'0'))),
                        CURDATE()
                      ) AS days_away
               FROM relationships WHERE birthday IS NOT NULL
               AND DATEDIFF(
                     DATE(CONCAT(YEAR(CURDATE()),'-',
                          LPAD(MONTH(birthday),2,'0'),'-',
                          LPAD(DAY(birthday),2,'0'))),
                     CURDATE()
                   ) BETWEEN 0 AND 30
               ORDER BY days_away ASC LIMIT 5"""
        )
        result["birthdays"] = cur.fetchall()

        cur.execute(
            "SELECT content, briefing_date, emailed FROM morning_briefings "
            "ORDER BY briefing_date DESC LIMIT 1"
        )
        result["morning_briefing"] = cur.fetchone()

        cur.execute(
            "SELECT pipeline, log_date, emails_processed, family_emails_found, "
            "action_items_created, rules_applied, followups_detected, briefing_emailed, status "
            "FROM daily_activity_log ORDER BY log_date DESC, logged_at DESC LIMIT 20"
        )
        result["activity_log"] = cur.fetchall()

        cur.close()
        conn.close()
    except Exception as e:
        logger.warning("Dashboard data fetch failed: %s", e)

    # Weather — live API call (no DB dependency)
    try:
        from app.pipelines.weather_pipeline import WeatherPipeline
        result["weather"] = WeatherPipeline().fetch()
    except Exception as e:
        logger.warning("Weather fetch failed: %s", e)

    return result


# ── Bootstrap ─────────────────────────────────────────────────────────────────

with app.app_context():
    try:
        init_db()
    except Exception as e:
        logger.warning("DB init skipped (will retry on first use): %s", e)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
