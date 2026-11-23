from backend.database.database import get_connection


def get_db():
    """One SQLite connection per request, always closed afterwards."""
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()
