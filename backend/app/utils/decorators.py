import re
import time
from functools import wraps
from collections import defaultdict, deque

from flask import request, g

from ..extensions import get_db
from .responses import unauthorized, forbidden, too_many
from .helpers import to_object_id

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,30}$")


def validate_email(email):
    return bool(email) and len(email) <= 254 and bool(EMAIL_RE.match(email))


def validate_username(username):
    return bool(username) and bool(USERNAME_RE.match(username))


def validate_password(password):
    return isinstance(password, str) and 8 <= len(password) <= 128


def validate_phone(phone):
    if not phone:
        return True
    return bool(re.match(r"^[+0-9][0-9\s-]{6,19}$", str(phone)))


def get_current_user():
    """Return the current user doc from g, or None."""
    return getattr(g, "current_user", None)


def load_current_user():
    """Before-request helper: decode JWT and attach user to g."""
    from flask import current_app
    import jwt

    g.current_user = None
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        return
    try:
        payload = jwt.decode(token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"])
        if payload.get("type") != "access":
            return
        user_id = to_object_id(payload.get("sub"))
        if not user_id:
            return
        user = get_db().users.find_one({"_id": user_id})
        if not user or user.get("status") != "active":
            return
        # Token version check: invalidates tokens issued before a password change
        if payload.get("tv", 0) != user.get("token_version", 0):
            return
        g.current_user = user
    except Exception:
        g.current_user = None


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return unauthorized()
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @auth_required
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user.get("role") not in roles:
                return forbidden()
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------- Rate limiting (in-memory, per-process) ----------------
_hits = defaultdict(deque)


def rate_limit(max_requests, window_seconds):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = request.remote_addr or "unknown"
            user = get_current_user()
            if user:
                key = f"u:{user['_id']}"
            now = time.time()
            q = _hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= max_requests:
                return too_many()
            q.append(now)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def reset_rate_limits():
    _hits.clear()
