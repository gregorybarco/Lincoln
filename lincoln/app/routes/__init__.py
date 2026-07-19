"""
Lincoln Flask Application Factory
===================================
Creates and configures the Flask application instance.
Registers all route blueprints and initialises the database on startup.
Called by bin\lincoln.bat via: python -m lincoln.app
"""
import io

from flask import Flask, send_file
from flask_socketio import SocketIO

from lincoln.lincoln_configuration import UI_HOST, UI_PORT
from lincoln.lincoln_database import initialise_database

socketio = SocketIO()


def create_app() -> Flask:
    """
    Create the configured Flask application.
    Initialises the SQLite database, registers all route blueprints,
    and attaches SocketIO for token streaming.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = "lincoln-local-only-no-network-exposure"

    # Initialise database on every startup — idempotent, safe to call repeatedly
    initialise_database()

    # ── Register route blueprints ─────────────────────────────────────────────
    from lincoln.app.routes.lincoln_routes_chat     import chat_blueprint
    from lincoln.app.routes.lincoln_routes_projects import projects_blueprint
    from lincoln.app.routes.lincoln_routes_models   import models_blueprint
    from lincoln.app.routes.lincoln_routes_settings import settings_blueprint
    from lincoln.app.routes.lincoln_routes_history  import history_blueprint
    from lincoln.app.routes.lincoln_routes_files    import files_blueprint

    app.register_blueprint(chat_blueprint)
    app.register_blueprint(projects_blueprint)
    app.register_blueprint(models_blueprint)
    app.register_blueprint(settings_blueprint)
    app.register_blueprint(history_blueprint)
    app.register_blueprint(files_blueprint)

    # ── Index route ───────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        from flask import render_template
        return render_template("lincoln_index.html")

    # ── Favicon — inline 1×1 transparent ICO, no file needed ─────────────────
    @app.route("/favicon.ico")
    def favicon():
        ico = bytes([
            0, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 24, 0, 40, 0,
            0, 0, 22, 0, 0, 0, 40, 0, 0, 0, 1, 0, 0, 0, 2, 0,
            0, 0, 1, 0, 24, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 255, 255,
            255, 0, 0, 0, 0, 255, 0, 0, 0, 255,
        ])
        return send_file(io.BytesIO(ico), mimetype="image/x-icon")

    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    return app


def run():
    """Entry point called by lincoln\\app\\__main__.py"""
    from lincoln.lincoln_configuration import print_startup_summary
    print_startup_summary()
    app = create_app()
    socketio.run(app, host=UI_HOST, port=UI_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    run()