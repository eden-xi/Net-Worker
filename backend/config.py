"""Runtime settings, read from environment variables on each call so tests
and deployments can change them without code changes."""

import os
import secrets

# Signing key for dev-mode session tokens. Random per process unless set, so
# dev tokens stop working when the server restarts.
_DEV_SECRET = os.environ.get("NETWORKER_SECRET") or secrets.token_urlsafe(32)

# Hosts allowed to embed the app in an iframe. Microsoft Teams and the
# Microsoft 365 apps that can host Teams tabs (Outlook, the M365 app).
DEFAULT_FRAME_ANCESTORS = [
    "'self'",
    "https://teams.microsoft.com",
    "https://*.teams.microsoft.com",
    "https://*.cloud.microsoft",
    "https://*.office.com",
    "https://*.office365.com",
    "https://*.microsoft365.com",
    "https://outlook.office.com",
    "https://outlook.office365.com",
    "https://*.skype.com",
]


def _flag(name, default):
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no", "off")


def _list(name):
    value = os.environ.get(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def auth_mode():
    """'dev' (sign in as a test user) or 'entra' (Microsoft Entra ID / Teams SSO)."""
    mode = os.environ.get("AUTH_MODE", "dev").strip().lower()
    if mode not in ("dev", "entra"):
        raise RuntimeError("AUTH_MODE must be 'dev' or 'entra'.")
    return mode


def dev_secret():
    return _DEV_SECRET


def dev_login_any_host():
    """Allow dev sign-in from other machines. Off: only from this computer."""
    return _flag("NETWORKER_DEV_LOGIN_ANY_HOST", "0")


def pm_self_service():
    """Let any signed-in user turn on project manager access for themselves."""
    return _flag("PM_SELF_SERVICE", "1")


def seed_samples():
    return _flag("NETWORKER_SEED_SAMPLES", "1")


def entra_tenant_id():
    return os.environ.get("ENTRA_TENANT_ID", "").strip()


def entra_audiences():
    """Accepted token audiences: the API's Application ID URI and client ID."""
    audiences = _list("ENTRA_AUDIENCE")
    client_id = os.environ.get("ENTRA_CLIENT_ID", "").strip()
    if client_id:
        audiences.append(client_id)
    return audiences


def frame_ancestors():
    return _list("NETWORKER_FRAME_ANCESTORS") or DEFAULT_FRAME_ANCESTORS


def cors_origins():
    return _list("NETWORKER_CORS_ORIGINS") or [
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ]


def validate():
    """Fail fast on settings that would leave the app insecure or broken."""
    if auth_mode() == "entra":
        missing = [
            name for name, value in [
                ("ENTRA_TENANT_ID", entra_tenant_id()),
                ("ENTRA_AUDIENCE or ENTRA_CLIENT_ID", entra_audiences()),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError(
                "AUTH_MODE=entra requires: " + ", ".join(missing)
            )
