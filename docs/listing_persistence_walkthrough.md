# Why Posted Listings Disappear on the Live Site

A plain-English explanation for the team: what happens to new listings on the Render demo site, when it happens, and how we can fix it.

## 1. The short version

- On the live site, anything you add (listings, applications, uploaded resumes) only lasts until the site **restarts**.
- On Render's **free plan** the site restarts often: after about **15 minutes with no visitors**, and on **every new deploy**.
- When it starts again, the database is empty, so the startup code loads the **10 demo projects** again. The site looks normal, but your listing is gone.
- Nothing is broken and nothing deleted it on purpose. This is how free hosting works.

## 2. Where the data actually lives

The app stores everything in one SQLite database file. On Render that file is inside the container:

```
/data/projecthub.db      <- listings, applications, statuses
/data/resumes/           <- uploaded resume files
```

A container is like a fresh copy of a computer made from our Dockerfile. On the free plan, its disk is **temporary**: it exists only while that copy is running. When Render throws the copy away and makes a new one, the disk starts empty again.

The real database and real resumes in our git repo are **never** copied into the container. That's on purpose, to keep private data off the internet. So every new copy starts with no data.

## 3. What happens, step by step

1. A manager signs in and posts a listing. It is saved to /data/projecthub.db inside the running container.
2. Everyone browses the site, and the listing shows up normally.
3. Nobody visits for about 15 minutes, so Render puts the service to sleep and the container is stopped.
4. Someone visits again. Render starts a **brand new** container from the image. Its /data folder is empty.
5. On startup, deploy/server.py creates empty tables, sees zero projects, and loads the 10 demo projects from deploy/demo_projects.csv.
6. The site shows the 10 demo projects only. The new listing is gone, and everyone is also signed out (sessions are kept in memory too).

The same thing happens straight away after a **new deploy** or a **manual restart** in the Render dashboard.

## 4. When it will happen

| Event | Data lost? | How often |
|---|---|---|
| No visitors for about 15 minutes | Yes | Many times a day |
| New deploy (we push code, or click Deploy) | Yes | Every deploy |
| Manual restart in the Render dashboard | Yes | Whenever someone restarts it |
| Render moves or restarts the server itself | Yes | Occasionally, without warning |
| People keep using the site | No | Data stays while it is awake |

The first visit after a sleep is also slow (often 30 to 60 seconds). That slow load is a good sign the site has restarted and the data has reset.

## 5. The other reason a listing can "disappear"

If a manager sets a listing to **Closed** or **Filled**, it is hidden from the shared browse feed, which only shows **Open** listings. That listing is **not** lost:

- It still appears in the manager's **Manage** tab.
- Setting it back to **Open** puts it back in the feed.

**Quick check:** if the Manage tab only shows the 10 demo projects, the site restarted. If your listing is there with a Closed or Filled status, it was the status.

## 6. How we can fix it

We need to keep the database **outside** the temporary container. There are two options:

| Option | What it means | Code changes | Cost | Needs team sign-off |
|---|---|---|---|---|
| A. Render persistent disk | Attach a disk at /data that survives restarts | None, the app already uses /data | Paid Render plan | Yes (budget) |
| B. Hosted database (Postgres) | Move listings and applications to a real database service | Yes, the database code changes | Free tiers exist | Yes (changes shared code) |

**Option A** is the smallest step. The container already keeps its data in /data (set by DATA_DIR in the Dockerfile), so attaching a disk there is a settings change in Render, not a code change. The free plan does not offer disks, and the service also still sleeps, but now it wakes up with the data still there.

**Option B** is the longer-term fix and is already in our "Round 2" plan. It changes the shared backend code, so we agree on it as a team first. Resume files would also need a storage service (for example, object storage) instead of a local folder.

Separately, logins are stored in memory, so people will always be signed out after a restart. That is fine for a demo and goes away once we use company sign-in (SSO).

## 7. What to tell people for now

- The live site is a **demo**. Listings and applications you add are temporary.
- They last until the site sleeps (about 15 minutes with no visitors) or we deploy new code.
- The 10 demo projects always come back, so the site is never empty.
- For a live demo, post the listing **during** the meeting, not beforehand.
- Do not put anything important or private on the live site until we pick Option A or B.

## 8. Files involved (nothing was changed)

| File | Its part in this |
|---|---|
| deploy/marketplace/Dockerfile | Sets DATA_DIR=/data, so the database lives in the container's /data folder |
| deploy/server.py | On startup, creates the tables and loads the demo projects if the database is empty |
| deploy/demo_projects.csv | The 10 demo projects that come back after every restart |
| backend/api/main.py | The browse feed only lists projects whose status is Open |
| marketplace/auth.py | Keeps login sessions in memory, so they reset on restart |
