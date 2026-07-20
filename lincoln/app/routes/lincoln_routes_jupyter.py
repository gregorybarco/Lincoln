from flask import Blueprint, jsonify, request
from lincoln.lincoln_jupyter_service import execute_code

jupyter_blueprint = Blueprint("jupyter", __name__)

@jupyter_blueprint.route("/api/jupyter/execute", methods=["POST"])
def run_code():
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    # Safely get the language, default to python if missing
    language = data.get("language", "python").strip()
    
    if not code:
        return jsonify({"error": "No code provided"}), 400
    
    try:
        # Pass BOTH code and language to the interceptor
        result = execute_code(code, language)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500