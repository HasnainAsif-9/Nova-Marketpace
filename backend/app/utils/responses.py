from flask import jsonify


def ok(data=None, message="Operation successful", status=200):
    payload = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def created(data=None, message="Created successfully"):
    return ok(data, message, 201)


def fail(message="Operation failed", error_code="ERROR", status=400, data=None):
    payload = {"success": False, "message": message, "error_code": error_code}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def unauthorized(message="Authentication required"):
    return fail(message, "UNAUTHORIZED", 401)


def forbidden(message="You do not have permission to perform this action"):
    return fail(message, "FORBIDDEN", 403)


def not_found(message="Resource not found"):
    return fail(message, "NOT_FOUND", 404)


def conflict(message="Resource already exists"):
    return fail(message, "CONFLICT", 409)


def too_many(message="Too many requests, please try again later"):
    return fail(message, "RATE_LIMITED", 429)


def server_error(message="Internal server error"):
    return fail(message, "INTERNAL_ERROR", 500)
