from datetime import datetime, timezone

from ..extensions import get_db


def audit_log(action, actor_id=None, actor_role=None, target_type=None,
              target_id=None, details=None, ip=None):
    """Write an audit log entry. Never log passwords or secrets."""
    try:
        get_db().audit_logs.insert_one({
            "action": action,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "target_type": target_type,
            "target_id": target_id,
            "details": details or {},
            "ip": ip,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        # Audit logging must never break the main request
        pass
