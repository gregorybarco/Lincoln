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
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = "lincoln-local-only-no-network-exposure"

    initialise_database()

    from lincoln.app.routes.lincoln_routes_chat     import chat_blueprint
    from lincoln.app.routes.lincoln_routes_projects import projects_blueprint
    from lincoln.app.routes.lincoln_routes_models   import models_blueprint
    from lincoln.app.routes.lincoln_routes_settings import settings_blueprint
    from lincoln.app.routes.lincoln_routes_history  import history_blueprint
    from lincoln.app.routes.lincoln_routes_files    import files_blueprint
    from lincoln.app.routes.lincoln_routes_jupyter  import jupyter_blueprint

    app.register_blueprint(chat_blueprint)
    app.register_blueprint(projects_blueprint)
    app.register_blueprint(models_blueprint)
    app.register_blueprint(settings_blueprint)
    app.register_blueprint(history_blueprint)
    app.register_blueprint(files_blueprint)
    app.register_blueprint(jupyter_blueprint)

    @app.route("/")
    def index():
        from flask import render_template
        return render_template("lincoln_index.html")

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

    @app.route("/api/files/browse")
    def browse_files():
        """
        Server-side file/folder browser for the New Project path picker.
        GET /api/files/browse?path=C:/Users/...
        Returns immediate children (dirs + files) of the requested path.
        """
        import os
        from flask import request, jsonify

        raw_path = request.args.get("path", "").strip()

        # Default: show drive roots on Windows
        if not raw_path:
            import string
            drives = [
                f"{d}:\\" for d in string.ascii_uppercase
                if os.path.exists(f"{d}:\\")
            ]
            return jsonify({"path": "", "parent": None, "entries": [
                {"name": d, "path": d, "type": "dir"} for d in drives
            ]})

        target = os.path.normpath(raw_path)
        if not os.path.isdir(target):
            return jsonify({"error": f"Not a directory: {target}"}), 400

        try:
            entries = []
            for name in sorted(os.listdir(target)):
                full = os.path.join(target, name)
                try:
                    entry_type = "dir" if os.path.isdir(full) else "file"
                    entries.append({"name": name, "path": full, "type": entry_type})
                except PermissionError:
                    pass

            parent = os.path.dirname(target)
            return jsonify({
                "path":    target,
                "parent":  parent if parent != target else None,
                "entries": entries,
            })
        except PermissionError:
            return jsonify({"error": "Permission denied"}), 403

    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    return app


def run():
    from lincoln.lincoln_configuration import print_startup_summary
    print_startup_summary()
    app = create_app()
    socketio.run(app, host=UI_HOST, port=UI_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    run()