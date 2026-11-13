"""
The activity log: one row in activity_events for every change anyone makes.

It powers two features from the same table:
  - recent()    the manager's live activity feed
  - timelines() each application's history, shown to the employee as a progress tracker

record() is always called INSIDE the caller's transaction, so the change and its log
line are saved together. A change that fails leaves no log line behind.
Later, the agent's actions are logged here too, so "what did the AI do?" has an answer.
"""

from backend.schemas.insights import ActivityKind

# ------------------------------------------
# 1. Writing
# ------------------------------------------

def record(db, kind, actor, project_id=None, application_id=None, from_status=None, to_status=None):
    """actor is the signed-in User who made the change. Does not commit (the caller's transaction does)."""
    db.execute("""
        INSERT INTO activity_events (kind, actor_email, actor_name, project_id, application_id,
                                     from_status, to_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (kind, actor.email, actor.name, project_id, application_id, from_status, to_status))


# ------------------------------------------
# 2. Reading: the activity feed
# ------------------------------------------

FEED_SQL = """
    SELECT activity_events.*, projects.title AS project_title, employees.name AS applicant_name
    FROM activity_events
    LEFT JOIN projects ON projects.id = activity_events.project_id
    LEFT JOIN applications ON applications.id = activity_events.application_id
    LEFT JOIN employees ON employees.id = applications.employee_id
"""


def describe(event):
    """Turn one event row into a sentence a person can read."""
    who = event["actor_name"] or event["actor_email"]
    listing = event["project_title"] or "a listing"
    applicant = event["applicant_name"] or "an applicant"
    kind = event["kind"]

    if kind == ActivityKind.LISTING_POSTED:
        return f"{who} posted {listing}"
    if kind == ActivityKind.LISTING_STATUS:
        return f"{who} marked {listing} as {event['to_status']}"
    if kind == ActivityKind.APPLICATION_SUBMITTED:
        return f"{who} applied to {listing}"
    if kind == ActivityKind.APPLICATION_STATUS:
        return f"{who} moved {applicant} on {listing} to {event['to_status']}"
    return f"{who} made a change"


def recent(db, after_id=0, limit=30):
    """The newest events, newest first. after_id lets the page ask only for what is new."""
    rows = db.execute(FEED_SQL + " WHERE activity_events.id > ? ORDER BY activity_events.id DESC LIMIT ?",
                      (after_id, limit)).fetchall()
    return [{**dict(row), "message": describe(row)} for row in rows]


# ------------------------------------------
# 3. Reading: application timelines
# ------------------------------------------

def timelines(db, application_ids):
    """{application_id: [steps, oldest first]} for many applications in ONE query."""
    steps = {application_id: [] for application_id in application_ids}
    if not application_ids:
        return steps

    placeholders = ", ".join("?" for _ in application_ids)
    rows = db.execute(f"""
        SELECT application_id, to_status, actor_name, created_at
        FROM activity_events
        WHERE application_id IN ({placeholders})
          AND kind IN (?, ?)
        ORDER BY id
    """, (*application_ids, ActivityKind.APPLICATION_SUBMITTED, ActivityKind.APPLICATION_STATUS)).fetchall()

    for row in rows:
        steps[row["application_id"]].append({
            "status": row["to_status"], "actor_name": row["actor_name"], "created_at": row["created_at"],
        })
    return steps
