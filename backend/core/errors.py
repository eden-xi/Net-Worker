"""
The errors our own code raises.

Services (the code that holds the SQL) raise these instead of HTTP errors, because
services don't know about HTTP: the same function is used by routes, tests, and
later the MCP server. backend/app.py turns each one into a response, once:

    NotFound  -> 404      Conflict -> 409      Invalid -> 400      TooLarge -> 413
    NotSignedIn -> 401    Forbidden -> 403   (raised by core/security.py)
"""


class AppError(Exception):
    status_code = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class Invalid(AppError):
    status_code = 400


class TooLarge(AppError):
    status_code = 413


class NotSignedIn(AppError):
    status_code = 401


class Forbidden(AppError):
    status_code = 403
