"""TopoTash / 拓事 — Flask application entry point.

Run:
    python app.py            # http://127.0.0.1:5000  (debug)
    python app.py init-db    # create topotash.db from schema.sql
    python app.py seed-demo  # optional sample data
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from db import ApiError, close_db, ensure_schema, get_db, init_db, utcnow
from services import (
    STAGE_HINTS,
    STAGE_LABELS,
    STAGES,
    STATUS_LABELS,
    STATUSES,
    diagram_dict,
    project_dict,
    project_stats,
)

BASE_DIR = Path(__file__).resolve().parent


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("TOPOTASH_SECRET", "topotash-local-dev"),
        DATABASE=os.environ.get("TOPOTASH_DB", str(BASE_DIR / "topotash.db")),
    )
    if test_config:
        app.config.update(test_config)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.teardown_appcontext(close_db)

    # First run convenience: create the schema when the DB is absent/empty.
    ensure_schema(app)

    from api import register_blueprints

    register_blueprints(app)

    @app.before_request
    def validate_api_body():
        if not request.path.startswith("/api/") or request.method not in {"POST", "PUT", "PATCH"}:
            return
        # CSV import uses multipart/form-data; the endpoint validates the file.
        if request.mimetype == "multipart/form-data":
            return
        data = request.get_json(silent=True)
        if request.get_data() and not isinstance(data, dict):
            raise ApiError("请求内容必须是 JSON 对象", 400, "invalid_json")

    @app.context_processor
    def inject_constants():
        return {
            "stages": [{"key": k, "label": STAGE_LABELS[k], "hint": STAGE_HINTS[k]} for k in STAGES],
            "stage_labels": STAGE_LABELS,
            "stage_hints": STAGE_HINTS,
            "statuses": [{"key": k, "label": STATUS_LABELS[k]} for k in STATUSES],
            "status_labels": STATUS_LABELS,
        }

    # ------------------------------------------------------------------ pages
    @app.get("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/board")
    def board():
        return render_template("board.html")

    @app.get("/diagrams")
    def diagrams_library():
        return render_template("diagrams.html")

    @app.get("/device-templates")
    def device_templates_page():
        return render_template("device_templates.html")

    @app.get("/projects/<project_id>")
    def project_page(project_id):
        row = get_db().execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return redirect(url_for("dashboard"))
        project = project_dict(row, project_stats(project_id))
        return render_template("project.html", project=project)

    @app.get("/projects/<project_id>/diagrams/<diagram_id>")
    def diagram_editor(project_id, diagram_id):
        project_row = get_db().execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        diagram_row = get_db().execute(
            "SELECT * FROM diagrams WHERE id=? AND project_id=?", (diagram_id, project_id)
        ).fetchone()
        if not project_row or not diagram_row:
            return redirect(url_for("dashboard"))
        project = project_dict(project_row, project_stats(project_id))
        diagram = diagram_dict(diagram_row)
        return render_template("editor.html", project=project, diagram=diagram)

    @app.get("/diagrams/<diagram_id>")
    def diagram_editor_library(diagram_id):
        """Editor for diagrams that live in the library without a project."""
        diagram_row = get_db().execute(
            "SELECT * FROM diagrams WHERE id=?", (diagram_id,)
        ).fetchone()
        if not diagram_row:
            return redirect(url_for("diagrams_library"))
        if diagram_row["project_id"]:
            return redirect(
                url_for(
                    "diagram_editor",
                    project_id=diagram_row["project_id"],
                    diagram_id=diagram_id,
                )
            )
        return render_template("editor.html", project=None, diagram=diagram_dict(diagram_row))

    @app.get("/healthz")
    def healthz():
        try:
            get_db().execute("SELECT 1").fetchone()
        except Exception as exc:  # pragma: no cover - diagnostics only
            return jsonify({"ok": False, "error": str(exc)}), 500
        return jsonify({
            "ok": True, "app": "TopoTash", "time": utcnow(),
            "database": str(Path(app.config["DATABASE"]).resolve()),
        })

    # ----------------------------------------------------------------- errors
    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError):
        return jsonify({"error": {"code": exc.code, "message": exc.message}}), exc.status

    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException):
        if request.path.startswith("/api/"):
            return (
                jsonify({"error": {"code": exc.name.lower().replace(" ", "_"), "message": exc.description}}),
                exc.code,
            )
        return exc

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):
        app.logger.exception("Unhandled error")
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "server_error", "message": str(exc)}}), 500
        return "<h1>500 Internal Server Error</h1><p>详情见 Flask 控制台。</p>", 500

    # -------------------------------------------------------------------- CLI
    @app.cli.command("init-db")
    def init_db_command():
        """Create the SQLite schema (idempotent)."""
        init_db(app)
        print(f"initialized database: {app.config['DATABASE']}")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Insert sample projects, tasks and diagrams."""
        from tools.seed_demo import seed_demo

        init_db(app)
        with app.app_context():
            created = seed_demo()
        print(f"seeded {created} projects")

    return app


app = create_app()


if __name__ == "__main__":
    # CLI compatibility: `python app.py init-db`
    if len(sys.argv) > 1 and sys.argv[1] in {"init-db", "seed-demo"}:
        with app.app_context():
            if sys.argv[1] == "init-db":
                init_db(app)
                print(f"initialized database: {app.config['DATABASE']}")
            else:
                from tools.seed_demo import seed_demo

                init_db(app)
                print(f"seeded {seed_demo()} projects")
        raise SystemExit(0)
    app.run(host="127.0.0.1", port=5000, debug=True)
