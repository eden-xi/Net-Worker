# Running ProjectHub in Microsoft Teams

ProjectHub runs as a Teams personal tab. Inside Teams it uses a compact
layout, follows the Teams theme, and signs users in silently with Teams
single sign-on (SSO), which gives the app a Microsoft Entra ID token.

Teams only loads tabs over HTTPS, so you need either a deployed server or an
HTTPS tunnel to your machine.

## 1. Get an HTTPS address

For development, tunnel your local server, for example with Microsoft Dev
Tunnels:

```bash
devtunnel host -p 8000 --allow-anonymous
```

Note the host name it prints (for example `abc123-8000.usw2.devtunnels.ms`).
Below, `HOSTNAME` means that host name, without `https://`.

## 2. Register the app in Microsoft Entra ID

In the Azure portal, under **Microsoft Entra ID > App registrations > New
registration**:

1. Name it ProjectHub. Supported account types: **this organizational
   directory only** (single tenant).
2. Note the **Application (client) ID** and **Directory (tenant) ID**.
3. **Expose an API**:
   - Set the Application ID URI to `api://HOSTNAME/CLIENT_ID`.
   - Add a scope named `access_as_user`, consent by admins and users.
   - Under **Authorized client applications**, add the Teams clients so they
     can get tokens without a consent prompt:
     - `1fec8e78-bce4-4aaf-ab1b-5451cc387264` (Teams desktop and mobile)
     - `5e3ce6c0-2b1f-4285-8d4b-75ee78787346` (Teams web)

     To also run in Outlook and the Microsoft 365 app, add the client IDs
     Microsoft lists in "Enable SSO for tab app" in the Teams docs.
4. Optional, **App roles**: create `ProjectManager` and `Admin` roles
   (allowed member type: users). Users assigned these roles in Entra get that
   access in ProjectHub automatically. Without them, people can still turn on
   PM access themselves (see `PM_SELF_SERVICE`), and admins can grant it in the
   app.

## 3. Start the server in Entra mode

```bash
AUTH_MODE=entra \
ENTRA_TENANT_ID=<tenant id> \
ENTRA_CLIENT_ID=<client id> \
ENTRA_AUDIENCE=api://HOSTNAME/<client id> \
NETWORKER_SEED_SAMPLES=0 \
uvicorn backend.api.main:app --port 8000
```

(On Windows PowerShell, set each with `$env:AUTH_MODE = "entra"` and so on.)

The server refuses to start in Entra mode if the tenant or audience is
missing. Tokens from any other tenant are rejected.

To test the Teams layout before setting up Entra, you can leave `AUTH_MODE`
as `dev`. You'll get the test-user picker inside Teams. Because the tunnel
forwards requests from this computer, dev sign-in will work through it, so
don't share a dev-mode tunnel URL.

## 4. Build and install the app package

1. Copy `manifest.json` and replace the placeholders:
   - `{{TEAMS_APP_ID}}`: a new GUID (for example from `[guid]::NewGuid()` in
     PowerShell).
   - `{{HOSTNAME}}`: your HTTPS host name.
   - `{{ENTRA_CLIENT_ID}}`: the client ID from step 2.
   - `{{COMPANY_NAME}}`: your organization.
2. Zip `manifest.json`, `color.png` and `outline.png` together, with no
   folder inside the zip.
3. In Teams, go to **Apps > Manage your apps > Upload an app > Upload a
   custom app** and choose the zip. (Your Teams admin may need to allow
   custom app uploads.)

## What the app does differently inside Teams

- The sidebar becomes a slim tab bar, and the ProjectHub brand is hidden
  because Teams already shows the app name.
- Light, dark and high-contrast themes follow the Teams setting and switch
  when it changes.
- Details and forms open in a side panel; there are no browser pop-up
  dialogs.
- The server sends `Content-Security-Policy: frame-ancestors` listing Teams
  and Microsoft 365 hosts, and no `X-Frame-Options` header. Override the list
  with `NETWORKER_FRAME_ANCESTORS` (comma-separated) if Microsoft adds hosts.
