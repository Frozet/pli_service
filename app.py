import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from flask import Flask, abort, current_app, g, redirect, render_template, request, send_from_directory, url_for
from psycopg2 import Error as DatabaseError
from psycopg2.pool import PoolError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from admin_views import bp as admin_bp
from attachments import AttachmentStore
from auth_views import bp as auth_bp
from createuser import create_admin
from database import Database, setting
from diagnostic_views import bp as diagnostics_bp
from security import csrf_token, load_user, password_hasher
from seed import seed_diagnostics

ROOT = Path(__file__).resolve().parent
PUBLIC_STATIC_EXTENSIONS = {".css", ".js", ".png", ".ico", ".svg", ".woff", ".woff2", ".map"}
SCHEMA_VERSION = "002_structured_diagnostics"


def create_app(config=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        SECRET_KEY=setting("SECRET_KEY"),
        SESSION_COOKIE_NAME="pli_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=setting("SESSION_COOKIE_SECURE", "1") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=32 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=256 * 1024,
        MAX_FORM_PARTS=1100,
        UPLOAD_FOLDER=setting("UPLOAD_FOLDER", str(ROOT / "instance" / "uploads")),
        LEGACY_UPLOAD_FOLDER=setting("LEGACY_UPLOAD_FOLDER", str(ROOT / "static" / "uploads")),
        YANDEX_MAPS_API_KEY=setting("YANDEX_MAPS_API_KEY"),
        TRUST_PROXY=setting("TRUST_PROXY", "0") == "1",
        TRUSTED_HOSTS=setting("TRUSTED_HOSTS", "").split() or None,
        DB_POOL_SIZE=4,
        DATABASE_DSN=None,
        PDF_TIMEOUT=30,
    )
    if config:
        app.config.update(config)
    if not app.secret_key or len(app.secret_key) < 32:
        raise RuntimeError("Set SECRET_KEY or SECRET_KEY_FILE to a new random key of at least 32 characters.")
    if app.config["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
    if app.config["YANDEX_MAPS_API_KEY"] is None:
        public_key = ROOT / "static" / "yandex_api_key.txt"
        if public_key.is_file():
            app.config["YANDEX_MAPS_API_KEY"] = public_key.read_text(encoding="utf-8").strip()

    upload_root = Path(app.config["UPLOAD_FOLDER"]).resolve()
    if upload_root.is_relative_to(ROOT / "static") or upload_root == Path(app.config["LEGACY_UPLOAD_FOLDER"]).resolve():
        raise RuntimeError("UPLOAD_FOLDER must be a private directory separate from the legacy upload directory.")
    store = AttachmentStore(upload_root, app.config["LEGACY_UPLOAD_FOLDER"])
    store.prepare()
    db = Database(app.config["DATABASE_DSN"], app.config["DB_POOL_SIZE"])
    app.extensions.update(
        attachments=store, db=db, dummy_password=password_hasher.hash("unused dummy password for timing")
    )
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(diagnostics_bp)
    app.cli.add_command(create_admin)
    app.cli.add_command(seed_diagnostics)
    app.before_request(load_account)
    app.after_request(response_headers)
    app.context_processor(template_context)
    app.add_template_filter(format_metres, "metres")
    app.register_error_handler(HTTPException, render_error)
    app.register_error_handler(DatabaseError, database_unavailable)
    app.register_error_handler(PoolError, database_unavailable)

    @app.get("/")
    @app.get("/index")
    def index():
        return render_template("index.html")

    @app.get("/about")
    def about():
        return render_template("about.html")

    @app.get("/static/<path:filename>", endpoint="static")
    def static_file(filename):
        folder = ROOT / "static"
        path = (folder / filename).resolve()
        if (not path.is_relative_to(folder) or path.is_relative_to(folder / "uploads")
                or path.is_relative_to(store.legacy_root) or filename.split("/")[0] == "uploads"
                or path.suffix.lower() not in PUBLIC_STATIC_EXTENSIONS):
            abort(404)
        return send_from_directory(folder, filename)

    @app.get("/ready")
    def ready():
        with db.transaction() as cursor:
            cursor.execute("SELECT 1 FROM pli_schema_migrations WHERE version = %s", (SCHEMA_VERSION,))
            if not cursor.fetchone():
                abort(503)
        if not os.access(store.root, os.W_OK | os.X_OK):
            abort(503)
        return {"status": "ok"}

    @app.cli.command("cleanup-files")
    def cleanup_files():
        store.drain_deletions(db)
        with db.transaction() as cursor:
            cursor.execute("DELETE FROM login_attempts WHERE expires_at < CURRENT_TIMESTAMP")

    return app


def load_account():
    if request.endpoint not in ("static", "ready"):
        load_user()


def response_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "private, no-store"
    return response


def template_context():
    return {
        "current_year": date.today().year,
        "csrf_token": csrf_token,
        "account": g.get("user"),
        "yandex_api_key": current_app.config["YANDEX_MAPS_API_KEY"],
    }


def format_metres(value):
    if value is None:
        return "—"
    return format(Decimal(str(value)).normalize(), "f")


def render_error(error):
    return render_template("error.html", message=error.description, status=error.code), error.code


def database_unavailable(error):
    current_app.logger.exception("Database request failed")
    return render_template("error.html", message="Сервис временно недоступен.", status=503), 503


if __name__ == "__main__":
    create_app().run(port=5001)
