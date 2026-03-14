"""Coast Capital Finance Platform — Flask Application Factory."""
import uuid
from datetime import datetime

from flask import Flask, g, jsonify, redirect, request
from app.config import settings
from app.utils.logging_config import setup_logging, get_logger
from app.utils.metrics import init_metrics

logger = get_logger(__name__)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    setup_logging()

    app = Flask(__name__)
    init_metrics(app, module="finance")
    app.config["SECRET_KEY"] = settings.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = settings.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JSON_SORT_KEYS"] = False

    # Initialize database
    with app.app_context():
        _init_database()

    # Register blueprints
    from app.routes.n8n_routes import n8n_bp
    from app.routes.api_routes import api_bp
    from app.routes.market_routes import market_bp
    from app.routes.model_routes import model_bp
    from app.agents.finance_agent import register_agent_routes
    app.register_blueprint(n8n_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(model_bp)
    register_agent_routes(app)

    # X-Request-ID header
    @app.before_request
    def _set_request_id():
        g.request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:8])

    @app.after_request
    def _add_request_id(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        return response

    # Global health endpoint
    @app.route("/health", methods=["GET"])
    def health():
        from app.models.database import check_db_health
        db_health = check_db_health()
        ok = db_health["status"] == "healthy"
        return jsonify({
            "status": "ok" if ok else "error",
            "service": "coastcapital-finance",
            "ts": datetime.now().isoformat(),
        }), 200 if ok else 503

    @app.route("/", methods=["GET"])
    def index():
        return redirect("/dashboard")

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.error("Unhandled server error", error=str(e))
        return jsonify({"success": False, "error": "Internal server error"}), 500

    logger.info("Coast Capital Finance Platform started",
               env=settings.FLASK_ENV,
               db=settings.MYSQL_DATABASE)

    return app


def _init_database():
    """Initialize database schema on startup."""
    try:
        from app.models.database import init_db
        init_db()
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        # Don't crash on startup — DB might need migration
