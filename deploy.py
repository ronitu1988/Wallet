import hmac
import os
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_from_directory,
    session,
)

import server as core


ROOT = Path(__file__).resolve().parent

# For free staging, this file is disposable.
# For a paid persistent disk, set DB_PATH to a path on that disk.
core.DB = Path(os.environ.get("DB_PATH", str(ROOT / "salon.db")))
core.DB.parent.mkdir(parents=True, exist_ok=True)
core.init()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=16_000,
)

# STAGING_PASSWORD = os.environ["STAGING_PASSWORD"]
PUBLIC_ORIGIN = os.environ["PUBLIC_ORIGIN"].rstrip("/")


# GATE_HTML = """
# <!doctype html>
# <html lang="en">
# <head>
#   <meta charset="utf-8">
#   <meta name="viewport" content="width=device-width, initial-scale=1">
#   <title>Lumi staging access</title>
# </head>
# <body style="background:#f5f5ef;color:#173a32;
#              font-family:system-ui;padding:10vh 24px">
#   <main style="max-width:400px;margin:auto">
#     <h1>Lumi staging</h1>
#     <p>Private development preview. Test funds only.</p>
#     <form method="post">
#       <label for="password">Staging access password</label>
#       <input id="password" name="password" type="password" required
#              autocomplete="current-password"
#              style="box-sizing:border-box;width:100%;
#                     padding:14px;margin:12px 0">
#       <button style="padding:12px 20px">Open preview</button>
#     </form>
#     {% if error %}<p role="alert">{{ error }}</p>{% endif %}
#   </main>
# </body>
# </html>
# """


# @app.before_request
# def protect_staging():
#     # Allow a host health check without exposing application data.
#     if request.path == "/healthz":
#         return None

#     # Require same-origin browser writes.
#     if request.method == "POST":
#         if request.headers.get("Origin") != PUBLIC_ORIGIN:
#             return jsonify(error="Invalid request origin"), 403

#     if request.path == "/preview-access":
#         return None

#     if not session.get("preview_access"):
#         if request.path.startswith("/api/"):
#             return jsonify(error="Open the staging access page first"), 401
#         return redirect("/preview-access")

@app.before_request
def validate_request_origin():
    if request.path == "/healthz":
        return None

    # Keep the same-origin protection for browser writes.
    if request.method == "POST":
        if request.headers.get("Origin") != PUBLIC_ORIGIN:
            return jsonify(error="Invalid request origin"), 403

@app.after_request
def security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.get("/healthz")
def health():
    return {"ok": True}


# @app.route("/preview-access", methods=["GET", "POST"])
# def preview_access():
#     error = None

#     if request.method == "POST":
#         supplied = request.form.get("password", "")
#         if hmac.compare_digest(
#             supplied.encode(),
#             STAGING_PASSWORD.encode(),
#         ):
#             session.clear()
#             session["preview_access"] = True
#             return redirect("/")

#         error = "Incorrect staging password."

#     return render_template_string(GATE_HTML, error=error)


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/app.js")
def javascript():
    return send_from_directory(ROOT, "app.js")


@app.get("/style.css")
def stylesheet():
    return send_from_directory(ROOT, "style.css")


@app.route("/api/<path:name>", methods=["GET", "POST"])
def api(name):
    # Reuse the existing business logic without starting its local HTTP server.
    handler = core.Handler.__new__(core.Handler)
    handler.headers = request.headers

    if request.method == "POST":
        if not request.is_json:
            return jsonify(error="JSON required"), 415
        body = request.get_json()
        if not isinstance(body, dict):
            return jsonify(error="JSON object required"), 400
    else:
        body = {}

    try:
        with core.connect() as database:
            database.execute("BEGIN IMMEDIATE")
            result = handler.route(
                database,
                request.method,
                "/api/" + name,
                body,
            )
        return jsonify(result)

    except core.Error as exc:
        return jsonify(error=exc.message), exc.status

    except (ValueError, KeyError, TypeError):
        return jsonify(error="Invalid request"), 400

    except Exception:
        app.logger.exception("Staging API error")
        return jsonify(error="Unexpected server error"), 500