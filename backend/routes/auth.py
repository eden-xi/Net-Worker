"""
Sign in, sign out, "who am I". Served under /api/auth/.
"""

from fastapi import APIRouter, HTTPException, Request, Response

from backend.core import config, security
from backend.schemas.users import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
def login(details: LoginRequest, response: Response):
    user = security.check_credentials(details.email, details.password, details.role)

    if user is None:
        raise HTTPException(status_code=401, detail="Wrong email, password, or role for this account.")

    response.set_cookie(
        config.COOKIE_NAME,
        security.start_session(user),
        max_age=config.SESSION_HOURS * 3600,
        httponly=True,                 # page JavaScript can't read it
        samesite="lax",                # other websites can't post with it
        secure=config.COOKIE_SECURE,   # HTTPS only on Render
    )
    return {"user": user, "login_mode": config.LOGIN_MODE}


@router.get("/me", response_model=LoginResponse)
def me(request: Request):
    user = security.get_session_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return {"user": user, "login_mode": config.LOGIN_MODE}


@router.get("/mode")
def mode():
    # Lets the login wall show the test-account hint only in test mode.
    return {"login_mode": config.LOGIN_MODE}


@router.post("/logout")
def logout(request: Request, response: Response):
    security.end_session(request.cookies.get(config.COOKIE_NAME))
    response.delete_cookie(config.COOKIE_NAME)
    return {"message": "Logged out."}
