"""User records. A user is identified by (auth_provider, external_id):
('dev', email) for test sign-in, ('entra', object id) for Microsoft Entra ID."""

from dataclasses import dataclass

ROLE_RANK = {"employee": 0, "pm": 1, "admin": 2}

# The owner of the bundled sample roles, also a dev sign-in user.
SAMPLE_OWNER = {
    "email": "priya.pm@example.com",
    "display_name": "Priya Patel",
    "role": "pm",
}

DEV_USERS = [
    {"email": "alex@example.com", "display_name": "Alex Rivera", "role": "employee"},
    SAMPLE_OWNER,
    {"email": "sam.pm@example.com", "display_name": "Sam Chen", "role": "pm"},
    {"email": "avery.admin@example.com", "display_name": "Avery Brooks", "role": "admin"},
]


@dataclass(frozen=True)
class User:
    id: int
    email: str
    display_name: str
    role: str

    def has_role(self, role):
        return ROLE_RANK[self.role] >= ROLE_RANK[role]


def avatar_version(filename):
    """A short token that changes whenever the picture changes, used to
    bust browser caches. None when the user has no picture."""
    return filename[:12] if filename else None


def higher_role(a, b):
    return a if ROLE_RANK[a] >= ROLE_RANK[b] else b


def to_user(row, role=None):
    return User(
        id=row["id"],
        email=row["email"] or "",
        display_name=row["display_name"] or row["email"] or "",
        role=role or row["role"],
    )


def get_user_row(connection, user_id):
    return connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_or_create_user(connection, provider, external_id, email, display_name, role="employee"):
    """Find a user by identity, creating them on first sign-in.

    Keeps email and display name in sync with the identity provider.
    """
    row = connection.execute(
        "SELECT * FROM users WHERE auth_provider = ? AND external_id = ?",
        (provider, external_id),
    ).fetchone()

    if row is None:
        connection.execute(
            """
            INSERT INTO users (auth_provider, external_id, email, display_name, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (provider, external_id, email, display_name, role),
        )
    elif (row["email"], row["display_name"]) != (email, display_name):
        connection.execute(
            """
            UPDATE users SET email = ?, display_name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (email, display_name, row["id"]),
        )

    connection.commit()

    return connection.execute(
        "SELECT * FROM users WHERE auth_provider = ? AND external_id = ?",
        (provider, external_id),
    ).fetchone()


def ensure_dev_user(connection, email, display_name, role):
    """Create a dev sign-in user if missing. Never changes an existing role."""
    email = email.strip().lower()
    return get_or_create_user(connection, "dev", email, email, display_name, role)
