import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = FLASK_ENV == "development"
    TESTING = False

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60"))
    JWT_REFRESH_TOKEN_EXPIRES_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "30"))

    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "novamarket")

    MARKETPLACE_NAME = os.getenv("MARKETPLACE_NAME", "NovaMarket")
    CURRENCY = os.getenv("CURRENCY", "PKR")
    CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "Rs.")
    DEFAULT_COMMISSION_RATE = float(os.getenv("DEFAULT_COMMISSION_RATE", "10"))
    DELIVERY_FEE_STANDARD = float(os.getenv("DELIVERY_FEE_STANDARD", "20"))
    DELIVERY_FEE_EXPRESS = float(os.getenv("DELIVERY_FEE_EXPRESS", "50"))
    FREE_DELIVERY_THRESHOLD = float(os.getenv("FREE_DELIVERY_THRESHOLD", "0"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "5")) * 1024 * 1024

    REQUIRE_SELLER_APPROVAL = _bool("REQUIRE_SELLER_APPROVAL", True)
    REQUIRE_PRODUCT_APPROVAL = _bool("REQUIRE_PRODUCT_APPROVAL", False)
    REQUIRE_EMAIL_VERIFICATION = _bool("REQUIRE_EMAIL_VERIFICATION", False)

    # Outbound email (password reset, verification). Empty SMTP_HOST = log-only (dev).
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "")
    FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5000")

    # Payments — comma-separated methods buyers may use at checkout.
    # A method only appears if its gateway credentials are also configured.
    PAYMENT_METHODS_ENABLED = [
        m.strip() for m in os.getenv("PAYMENT_METHODS_ENABLED", "cod").split(",") if m.strip()
    ]
    # TODO(payment): provider credentials — implement adapters in
    # app/payments/gateway.py once keys are issued.
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    JAZZCASH_MERCHANT_ID = os.getenv("JAZZCASH_MERCHANT_ID", "")
    JAZZCASH_PASSWORD = os.getenv("JAZZCASH_PASSWORD", "")
    JAZZCASH_INTEGRITY_SALT = os.getenv("JAZZCASH_INTEGRITY_SALT", "")
    EASYPAISA_STORE_ID = os.getenv("EASYPAISA_STORE_ID", "")
    EASYPAISA_HASH_KEY = os.getenv("EASYPAISA_HASH_KEY", "")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = FLASK_ENV == "production"

    # Frontend directory served by Flask
    FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

    @classmethod
    def validate(cls):
        """Refuse to run in production with default/weak secrets."""
        if cls.FLASK_ENV == "production" and not cls.TESTING:
            weak = []
            if cls.SECRET_KEY == "dev-secret-key-change-me":
                weak.append("SECRET_KEY")
            if cls.JWT_SECRET_KEY == "dev-jwt-secret-change-me":
                weak.append("JWT_SECRET_KEY")
            if weak:
                raise RuntimeError(
                    f"Production startup blocked: {', '.join(weak)} still uses the "
                    "development default. Set strong random values in the environment."
                )


class TestConfig(Config):
    TESTING = True
    DEBUG = True
    MONGODB_URI = "mongomock://localhost"
