"""REST API blueprints."""
from __future__ import annotations


def register_blueprints(app):
    from .projects import bp as projects_bp
    from .tasks import bp as tasks_bp
    from .diagrams import bp as diagrams_bp
    from .views import bp as views_bp
    from .ai import bp as ai_bp

    app.register_blueprint(projects_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(diagrams_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(ai_bp)
