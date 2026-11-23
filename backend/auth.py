"""Authentication. Every route gets the signed-in user from get_current_user;
nothing else knows which identity provider is in use.

AUTH_MODE=dev    Bearer tokens issued by /auth/dev-login (test users).
AUTH_MODE=entra  Bearer tokens from Microsoft Entra ID, such as the Teams SSO
                 token from microsoftTeams.authentication.getAuthToken().
"""

import time

import jwt
from fastapi import Depends, Header, HTTPException

from backend import config
from backend.database.database import get_connection
from backend.users import get_or_create_user, get_user_row, higher_role, to_user

DEV_TOKEN_ISSUER = "networker-dev"
DEV_TOKEN_LIFETIME = 8 * 60 * 60

# App roles defined on the Entra app registration, mapped to app roles.
ENTRA_ROLE_MAP = {"Admin": "admin", "ProjectManager": "pm"}


def unauthorized(detail="Please sign in."):
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


# ==========================================
# DEV TOKENS
# ==========================================

def issue_dev_token(user_id):
    now = int(time.time())
    return jwt.encode(
        {"sub": str(user_id), "iss": DEV_TOKEN_ISSUER, "iat": now, "exp": now + DEV_TOKEN_LIFETIME},
        config.dev_secret(),
        algorithm="HS256",
    )


def _user_from_dev_token(token):
    try:
        claims = jwt.decode(
            token, config.dev_secret(), algorithms=["HS256"], issuer=DEV_TOKEN_ISSUER,
            options={"require": ["sub", "exp", "iss"]},
        )
    except jwt.PyJWTError:
        raise unauthorized("Your session has expired. Please sign in again.")

    connection = get_connection()
    try:
        row = get_user_row(connection, int(claims["sub"]))
    finally:
        connection.close()

    if row is None:
        raise unauthorized()

    return to_user(row)


# ==========================================
# MICROSOFT ENTRA ID TOKENS
# ==========================================

class EntraVerifier:
    """Validates Entra ID access tokens for this app's API.

    Accepts v1 and v2 tokens from the configured tenant only. Signing keys
    come from the tenant's published JWKS and are cached.
    """

    def __init__(self, tenant_id, audiences, jwks_client=None):
        self.tenant_id = tenant_id
        self.audiences = audiences
        self.issuers = {
            f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            f"https://sts.windows.net/{tenant_id}/",
        }
        self.jwks_client = jwks_client or jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
            cache_keys=True,
            lifespan=6 * 60 * 60,
        )

    def verify(self, token):
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audiences,
                options={"require": ["exp", "iat", "aud", "iss", "tid", "oid"]},
                leeway=60,
            )
        except jwt.PyJWTError:
            raise unauthorized("Your Microsoft sign-in could not be verified.")

        if claims["iss"] not in self.issuers or claims["tid"] != self.tenant_id:
            raise unauthorized("This account's organization is not allowed.")

        return claims


_entra_verifier = None


def get_entra_verifier():
    global _entra_verifier
    tenant, audiences = config.entra_tenant_id(), config.entra_audiences()

    if (
        _entra_verifier is None
        or _entra_verifier.tenant_id != tenant
        or _entra_verifier.audiences != audiences
    ):
        _entra_verifier = EntraVerifier(tenant, audiences)

    return _entra_verifier


def set_entra_verifier(verifier):
    """Replace the verifier (used by tests)."""
    global _entra_verifier
    _entra_verifier = verifier


def _user_from_entra_token(token):
    claims = get_entra_verifier().verify(token)

    email = (
        claims.get("preferred_username") or claims.get("upn") or claims.get("email") or ""
    ).lower()
    name = claims.get("name") or email

    connection = get_connection()
    try:
        row = get_or_create_user(connection, "entra", claims["oid"], email, name)
    finally:
        connection.close()

    # An Entra app role can raise, but never lower, the role stored here.
    role = row["role"]
    for entra_role in claims.get("roles", []):
        if entra_role in ENTRA_ROLE_MAP:
            role = higher_role(role, ENTRA_ROLE_MAP[entra_role])

    return to_user(row, role)


# ==========================================
# FASTAPI DEPENDENCIES
# ==========================================

def get_current_user(authorization: str | None = Header(None)):
    scheme, _, token = (authorization or "").partition(" ")

    if scheme.lower() != "bearer" or not token:
        raise unauthorized()

    if config.auth_mode() == "entra":
        return _user_from_entra_token(token.strip())

    return _user_from_dev_token(token.strip())


def require_pm(user=Depends(get_current_user)):
    if not user.has_role("pm"):
        raise HTTPException(403, "Project manager access is required to post projects.")
    return user


def require_admin(user=Depends(get_current_user)):
    if not user.has_role("admin"):
        raise HTTPException(403, "Administrator access is required.")
    return user
