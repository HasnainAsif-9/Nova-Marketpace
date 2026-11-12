from flask import Blueprint, request, make_response, current_app
from datetime import datetime, timedelta, timezone
import hashlib
import jwt
import secrets
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

from ..extensions import get_db
from ..utils.responses import ok, fail, created, unauthorized
from ..utils.helpers import serialize, clean_str
from ..utils.decorators import (
    validate_email, validate_username, validate_password, validate_phone,
    rate_limit, get_current_user,
)
from ..utils.audit import audit_log
from ..utils.mailer import send_email
from ..utils.email_templates import verification_email, password_reset_email

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def _issue_tokens(user):
    now = datetime.now(timezone.utc)
    access_exp = now + timedelta(minutes=current_app.config["JWT_ACCESS_TOKEN_EXPIRES_MINUTES"])
    refresh_exp = now + timedelta(days=current_app.config["JWT_REFRESH_TOKEN_EXPIRES_DAYS"])
    access = jwt.encode(
        {"sub": str(user["_id"]), "role": user["role"], "type": "access",
         "tv": user.get("token_version", 0), "iat": now, "exp": access_exp},
        current_app.config["JWT_SECRET_KEY"], algorithm="HS256",
    )
    refresh = jwt.encode(
        {"sub": str(user["_id"]), "type": "refresh",
         "tv": user.get("token_version", 0), "iat": now, "exp": refresh_exp},
        current_app.config["JWT_SECRET_KEY"], algorithm="HS256",
    )
    return access, refresh, access_exp, refresh_exp


def _set_auth_cookies(response, access, refresh, access_exp, refresh_exp):
    secure = current_app.config["SESSION_COOKIE_SECURE"]
    response.set_cookie(ACCESS_COOKIE, access, expires=access_exp, httponly=True,
                        samesite="Lax", secure=secure, path="/")
    response.set_cookie(REFRESH_COOKIE, refresh, expires=refresh_exp, httponly=True,
                        samesite="Lax", secure=secure, path="/api/auth")
    return response


def _public_user(user):
    data = serialize(user)
    data.pop("password_hash", None)
    return data


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _send_verification_email(user):
    """Create a verification token and email the link. Never raises."""
    try:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        get_db().email_verifications.insert_one({
            "token_hash": _hash_token(token),
            "user_id": user["_id"],
            "expires_at": now + timedelta(hours=24),
            "used": False,
            "created_at": now,
        })
        link = f"{current_app.config['FRONTEND_BASE_URL']}/verify-email.html?token={token}"
        subject, text, html = verification_email(
            user.get("full_name") or user["username"], link)
        send_email(user["email"], subject, text, html=html)
    except Exception:
        current_app.logger.exception("Failed to send verification email")


@bp.post("/register")
@rate_limit(10, 60)
def register():
    data = request.get_json(silent=True) or {}
    username = clean_str(data.get("username"), 30)
    email_raw = clean_str(data.get("email"), 254)
    email = email_raw.lower() if email_raw else None
    password = data.get("password")
    full_name = clean_str(data.get("full_name"), 120)
    phone = clean_str(data.get("phone"), 20)
    role = data.get("role", "buyer")

    if role not in ("buyer", "seller"):
        return fail("Invalid role", "VALIDATION", 400)
    if not validate_username(username):
        return fail("Username must be 3-30 characters (letters, numbers, _ . -)", "VALIDATION", 400)
    if not validate_email(email):
        return fail("A valid email is required", "VALIDATION", 400)
    if not validate_password(password):
        return fail("Password must be at least 8 characters", "VALIDATION", 400)
    if phone and not validate_phone(phone):
        return fail("Invalid phone number", "VALIDATION", 400)

    db = get_db()
    if db.users.find_one({"username": username}):
        return fail("Username is already taken", "USERNAME_TAKEN", 409)
    if db.users.find_one({"email": email}):
        return fail("Email is already registered", "EMAIL_TAKEN", 409)

    now = datetime.now(timezone.utc)
    user_doc = {
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password),
        "full_name": full_name or username,
        "phone": phone,
        "role": role,
        "status": "active",
        "email_verified": False,
        "created_at": now,
        "updated_at": now,
    }
    result = db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    if role == "seller":
        store_name = clean_str(data.get("store_name"), 120) or f"{username}'s Store"
        db.sellers.insert_one({
            "user_id": result.inserted_id,
            "store_name": store_name,
            "store_slug": None,
            "description": clean_str(data.get("store_description"), 1000),
            "status": "pending" if current_app.config["REQUIRE_SELLER_APPROVAL"] else "approved",
            "status_reason": None,
            "created_at": now,
            "updated_at": now,
        })

    audit_log("user.register", actor_id=result.inserted_id, actor_role=role,
              target_type="user", target_id=str(result.inserted_id),
              details={"username": username}, ip=request.remote_addr)

    _send_verification_email(user_doc)

    access, refresh, aexp, rexp = _issue_tokens(user_doc)
    resp = make_response(ok({"user": _public_user(user_doc), "access_token": access},
                            "Registration successful", 201))
    return _set_auth_cookies(resp, access, refresh, aexp, rexp)


@bp.post("/login")
@rate_limit(10, 60)
def login():
    data = request.get_json(silent=True) or {}
    identifier = clean_str(data.get("email") or data.get("username"), 254)
    password = data.get("password")

    if not identifier or not password:
        return fail("Email/username and password are required", "VALIDATION", 400)

    db = get_db()
    ident_lower = identifier.lower()
    user = db.users.find_one({
        "$or": [{"email": identifier}, {"email": ident_lower},
                {"username": identifier}]
    })
    if not user or not check_password_hash(user["password_hash"], password):
        audit_log("auth.login_failed", details={"identifier": identifier},
                  ip=request.remote_addr)
        return unauthorized("Invalid credentials")

    if user.get("status") != "active":
        return fail("This account is not active. Please contact support.", "ACCOUNT_INACTIVE", 403)

    if (current_app.config.get("REQUIRE_EMAIL_VERIFICATION")
            and not user.get("email_verified")):
        return fail("Please verify your email address before signing in. "
                    "Check your inbox or request a new verification email.",
                    "EMAIL_NOT_VERIFIED", 403)

    if user["role"] == "seller":
        seller = db.sellers.find_one({"user_id": user["_id"]})
        if seller and seller.get("status") == "suspended":
            return fail("Your seller account has been suspended", "ACCOUNT_SUSPENDED", 403)

    db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": datetime.now(timezone.utc)}})
    audit_log("auth.login", actor_id=user["_id"], actor_role=user["role"],
              target_type="user", target_id=str(user["_id"]), ip=request.remote_addr)

    access, refresh, aexp, rexp = _issue_tokens(user)
    resp = make_response(ok({"user": _public_user(user), "access_token": access}, "Login successful"))
    return _set_auth_cookies(resp, access, refresh, aexp, rexp)


@bp.post("/logout")
def logout():
    resp = make_response(ok(message="Logged out"))
    resp.delete_cookie(ACCESS_COOKIE, path="/")
    resp.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return resp


@bp.post("/refresh")
@rate_limit(30, 60)
def refresh():
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        return unauthorized("No refresh token")
    try:
        payload = jwt.decode(token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"])
        if payload.get("type") != "refresh":
            return unauthorized("Invalid token type")
        user = get_db().users.find_one({"_id": ObjectId(payload["sub"])})
        if not user or user.get("status") != "active":
            return unauthorized("Account not active")
        if payload.get("tv", 0) != user.get("token_version", 0):
            return unauthorized("Token revoked")
    except Exception:
        return unauthorized("Invalid or expired refresh token")

    access, refresh, aexp, rexp = _issue_tokens(user)
    resp = make_response(ok({"access_token": access}, "Token refreshed"))
    return _set_auth_cookies(resp, access, refresh, aexp, rexp)


@bp.get("/me")
def me():
    user = get_current_user()
    if not user:
        return ok({"user": None})
    return ok({"user": _public_user(user)})


@bp.post("/change-password")
@rate_limit(5, 60)
def change_password():
    user = get_current_user()
    if not user:
        return unauthorized()
    data = request.get_json(silent=True) or {}
    current = data.get("current_password")
    new = data.get("new_password")
    if not current or not check_password_hash(user["password_hash"], current):
        return fail("Current password is incorrect", "VALIDATION", 400)
    if not validate_password(new):
        return fail("New password must be at least 8 characters", "VALIDATION", 400)
    get_db().users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": generate_password_hash(new),
                  "updated_at": datetime.now(timezone.utc)},
         "$inc": {"token_version": 1}}
    )
    audit_log("auth.password_change", actor_id=user["_id"], actor_role=user["role"],
              target_type="user", target_id=str(user["_id"]), ip=request.remote_addr)
    return ok(message="Password changed")


# ---------- Password reset ----------

@bp.post("/forgot-password")
@rate_limit(5, 60)
def forgot_password():
    """Request a password reset link. Always returns success to prevent
    user enumeration — the email is only sent if the account exists."""
    data = request.get_json(silent=True) or {}
    email = clean_str(data.get("email"), 254)
    if not email:
        return fail("Email is required", "VALIDATION", 400)

    db = get_db()
    user = db.users.find_one({"email": email.lower()})
    if user:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        db.password_resets.insert_one({
            "token_hash": _hash_token(token),
            "user_id": user["_id"],
            "expires_at": now + timedelta(hours=1),
            "used": False,
            "created_at": now,
        })
        link = f"{current_app.config['FRONTEND_BASE_URL']}/reset-password.html?token={token}"
        subject, text, html = password_reset_email(
            user.get("full_name") or user["username"], link)
        send_email(user["email"], subject, text, html=html)
        audit_log("auth.password_reset_requested", actor_id=user["_id"],
                  actor_role=user["role"], target_type="user", target_id=str(user["_id"]),
                  ip=request.remote_addr)
    return ok(message="If an account exists for that email, a reset link has been sent.")


@bp.post("/reset-password")
@rate_limit(10, 60)
def reset_password():
    data = request.get_json(silent=True) or {}
    token = clean_str(data.get("token"), 200)
    new = data.get("new_password")
    if not token:
        return fail("Reset token is required", "VALIDATION", 400)
    if not validate_password(new):
        return fail("Password must be at least 8 characters", "VALIDATION", 400)

    db = get_db()
    record = db.password_resets.find_one({"token_hash": _hash_token(token)})
    now = datetime.now(timezone.utc)
    if (not record or record.get("used")
            or record["expires_at"].replace(tzinfo=timezone.utc) < now):
        return fail("This reset link is invalid or has expired", "INVALID_TOKEN", 400)

    user = db.users.find_one({"_id": record["user_id"]})
    if not user:
        return fail("This reset link is invalid or has expired", "INVALID_TOKEN", 400)

    db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": generate_password_hash(new),
                  "updated_at": now},
         "$inc": {"token_version": 1}})
    db.password_resets.update_one({"_id": record["_id"]}, {"$set": {"used": True}})
    audit_log("auth.password_reset", actor_id=user["_id"], actor_role=user["role"],
              target_type="user", target_id=str(user["_id"]), ip=request.remote_addr)
    return ok(message="Password has been reset. Please sign in.")


# ---------- Email verification ----------

@bp.post("/verify-email")
@rate_limit(10, 60)
def verify_email():
    data = request.get_json(silent=True) or {}
    token = clean_str(data.get("token"), 200)
    if not token:
        return fail("Verification token is required", "VALIDATION", 400)

    db = get_db()
    record = db.email_verifications.find_one({"token_hash": _hash_token(token)})
    now = datetime.now(timezone.utc)
    if (not record or record.get("used")
            or record["expires_at"].replace(tzinfo=timezone.utc) < now):
        return fail("This verification link is invalid or has expired", "INVALID_TOKEN", 400)

    user = db.users.find_one({"_id": record["user_id"]})
    if not user:
        return fail("This verification link is invalid or has expired", "INVALID_TOKEN", 400)

    db.users.update_one({"_id": user["_id"]},
                        {"$set": {"email_verified": True, "updated_at": now}})
    db.email_verifications.update_one({"_id": record["_id"]}, {"$set": {"used": True}})
    audit_log("auth.email_verified", actor_id=user["_id"], actor_role=user["role"],
              target_type="user", target_id=str(user["_id"]), ip=request.remote_addr)
    return ok(message="Email verified successfully")


@bp.post("/resend-verification")
@rate_limit(5, 60)
def resend_verification():
    user = get_current_user()
    if not user:
        return unauthorized()
    if user.get("email_verified"):
        return ok(message="Email is already verified")
    _send_verification_email(user)
    return ok(message="Verification email sent")
