import os

from flask import Flask, send_from_directory, request, g
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import init_db
from .utils.decorators import load_current_user
from .utils.responses import fail, server_error, not_found


def create_app(config_class=Config):
    app = Flask(__name__,
                static_folder=os.path.join(config_class.FRONTEND_DIR, "assets"),
                static_url_path="/assets")
    app.config.from_object(config_class)
    config_class.validate()

    init_db(app)

    # Security headers + caching + compression
    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if app.config["FLASK_ENV"] == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Static assets: cache for 1 day (filenames are not fingerprinted)
        if request.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
        # HTML pages: always revalidate so deploys take effect immediately
        elif response.content_type and "text/html" in response.content_type:
            response.headers["Cache-Control"] = "no-cache"

        # Gzip compress text responses when the client accepts it.
        # Skip direct-passthrough (send_file/send_from_directory) and streamed
        # responses — get_data() raises RuntimeError on those.
        if (response.status_code < 300
                and not response.direct_passthrough
                and not response.is_streamed
                and "Content-Encoding" not in response.headers
                and "gzip" in request.headers.get("Accept-Encoding", "")
                and response.content_type
                and any(t in response.content_type for t in
                        ("text/", "application/json", "application/javascript",
                         "image/svg+xml"))
                and len(response.get_data()) > 500):
            import gzip as _gzip
            response.set_data(_gzip.compress(response.get_data(), compresslevel=6))
            response.headers["Content-Encoding"] = "gzip"
            response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers.add("Vary", "Accept-Encoding")
        return response

    # Load current user from JWT on every request
    @app.before_request
    def before_request():
        if request.path.startswith("/api/"):
            load_current_user()

    # Maintenance mode check
    @app.before_request
    def maintenance_check():
        if request.path.startswith("/api/") and request.path != "/api/settings":
            try:
                from .extensions import get_db
                s = get_db().settings.find_one({"key": "marketplace"})
                if s and s.get("maintenance_mode"):
                    user = getattr(g, "current_user", None)
                    if not user or user.get("role") != "admin":
                        return fail("Marketplace is under maintenance. Please check back soon.",
                                    "MAINTENANCE", 503)
            except Exception:
                pass

    # Register blueprints
    from .auth.routes import bp as auth_bp
    from .users.routes import bp as users_bp
    from .buyers.routes import bp as buyers_bp
    from .sellers.routes import bp as sellers_bp
    from .admin.routes import bp as admin_bp
    from .products.routes import bp as products_bp
    from .categories.routes import bp as categories_bp
    from .cart.routes import bp as cart_bp
    from .wishlist.routes import bp as wishlist_bp
    from .orders.routes import bp as orders_bp
    from .payments.routes import bp as payments_bp
    from .commissions.routes import bp as commissions_bp
    from .reviews.routes import bp as reviews_bp
    from .notifications.routes import bp as notifications_bp
    from .reports.routes import bp as reports_bp
    from .settings.routes import bp as settings_bp

    for bp in (auth_bp, users_bp, buyers_bp, sellers_bp, admin_bp,
               products_bp, categories_bp, cart_bp, wishlist_bp,
               orders_bp, payments_bp, commissions_bp, reviews_bp,
               notifications_bp, reports_bp, settings_bp):
        app.register_blueprint(bp)
    # Health check (no auth, no DB dependency)
    @app.route("/api/health")
    def health():
        return {"success": True, "data": {"status": "ok"}}

    # Serve frontend pages
    @app.route("/")
    def index():
        return send_from_directory(app.config["FRONTEND_DIR"], "index.html")

    @app.route("/<path:filename>")
    def serve_frontend(filename):
        # Only serve known frontend files (html pages), not arbitrary paths
        if filename.endswith(".html") or filename in (
            "robots.txt", "sitemap.xml"
        ):
            return send_from_directory(app.config["FRONTEND_DIR"], filename)
        # API 404 for unknown /api paths
        if filename.startswith("api/"):
            return not_found("API endpoint not found")
        return not_found("Page not found")

    # Error handlers
    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith("/api/"):
            return not_found("Resource not found")
        return send_from_directory(app.config["FRONTEND_DIR"], "404.html") \
            if _exists(app.config["FRONTEND_DIR"], "404.html") else ("Page not found", 404)

    @app.errorhandler(405)
    def handle_405(e):
        if request.path.startswith("/api/"):
            return fail("Method not allowed", "METHOD_NOT_ALLOWED", 405)
        return ("Method not allowed", 405)

    @app.errorhandler(413)
    def handle_413(e):
        return fail("Request entity too large", "PAYLOAD_TOO_LARGE", 413)

    @app.errorhandler(429)
    def handle_429(e):
        return fail("Too many requests", "RATE_LIMITED", 429)

    @app.errorhandler(500)
    def handle_500(e):
        app.logger.exception("Internal server error")
        if request.path.startswith("/api/"):
            return server_error()
        return ("Internal server error", 500)

    @app.errorhandler(Exception)
    def handle_exception(e):
        if isinstance(e, HTTPException):
            if request.path.startswith("/api/"):
                return fail(e.description or "HTTP error", "HTTP_ERROR", e.code or 500)
            return e
        app.logger.exception("Unhandled exception")
        if request.path.startswith("/api/"):
            return server_error()
        return ("Internal server error", 500)

    return app


def _exists(directory, filename):
    import os
    return os.path.isfile(os.path.join(directory, filename))
