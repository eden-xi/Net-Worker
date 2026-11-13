"""
Data shapes for people and logins.

  Role           employee (seeking projects) or manager (posting projects / admin)
  User           who is signed in. Kept in the session; never taken from a form.
  LoginRequest   what the login wall sends
  ProfileIn/Out  an employee's skills (used for "% match") and whether a resume is on file
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Role(StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"


class User(BaseModel):
    email: str
    name: str
    role: Role


class LoginRequest(BaseModel):
    email: str
    password: str
    role: Role

    @field_validator("email")
    @classmethod
    def clean_email(cls, value):
        value = value.strip().lower()
        name, at, domain = value.partition("@")
        if not name or not at or "." not in domain:
            raise ValueError("Please enter a valid email address.")
        return value


class LoginResponse(BaseModel):
    user: User
    login_mode: str


class ProfileIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    skills: str = Field("", max_length=500)


class ProfileOut(BaseModel):
    skills: str
    resume_on_file: bool
