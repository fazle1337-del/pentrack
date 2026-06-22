# Testing Entra SSO without an Entra tenant (Keycloak in the home lab)

The app speaks standard OpenID Connect, so it can't tell Keycloak from Entra —
only the `OIDC_AUTHORITY` URL differs. We test the full flow against a local
Keycloak, then flip the authority to the real tenant for production.

## How the flow works

1. Frontend shows **Sign in with Microsoft** when `GET /auth/config` reports
   `sso_enabled: true`. The button is a plain link to `/api/auth/sso/login`.
2. `/auth/sso/login` redirects the browser to the provider's `/authorize`
   (auth-code flow; nonce signed into the OAuth `state`, so no server session).
3. User authenticates at the provider, which redirects to
   `/auth/sso/callback?code=...`.
4. The backend exchanges the code, validates the `id_token` (signature via the
   provider JWKS, plus `iss`/`aud`/`exp`/`nonce`), reads the **groups** claim,
   and looks each group up in the `idp_role_maps` table.
5. The highest-privilege matched role wins; the user is created/updated
   (`auth_type=sso`), and the backend issues **its own** app JWT — the same one
   `/auth/login` issues — handed back to the SPA in the URL fragment.
6. The SPA (`consumeSsoRedirect`) reads `#sso_token=...`, stores it in memory,
   and scrubs the URL. A user whose groups map to no role gets `#sso_error=no_role`.

Because step 5 reissues the app's own JWT, every existing endpoint, `get_current_user`,
and `require_admin` are unchanged — SSO is just another way to mint that token.

## Run it locally

Keycloak and the api container must reach Keycloak at the **same URL** (token
issuer must match on both sides), so use your machine's LAN IP, not `localhost`.

```bash
export LAN_IP=192.168.1.50   # your dev box's LAN IP
docker compose -f docker-compose.yml -f docker-compose.sso-dev.yml up --build
# Frontend (separate shell), bound to the LAN so the redirect URIs resolve:
cd frontend && npm run dev -- --host
```

- Keycloak admin console: `http://<LAN_IP>:8081` (admin / admin)
- App: `http://<LAN_IP>:5173`
- Test users (password `password`): **alice** → `pentrack-admins` (admin),
  **bob** → `pentrack-members` (member)

Click **Sign in with Microsoft**, authenticate as alice or bob, and you should
land back in the app authenticated with the matching role.

The realm (`docs/keycloak/pentrack-realm.json`) is auto-imported with a
confidential client (`pentrack` / secret `pentrack-dev-secret`), two groups, a
group-membership mapper emitting a `groups` claim (full paths like
`/pentrack-admins`), and the two users. The `OIDC_BOOTSTRAP_*` env vars seed the
two `idp_role_maps` rows on first boot so login works with zero manual setup.

> The realm export uses `redirectUris: ["*"]` / `webOrigins: ["*"]` — fine for a
> throwaway lab realm, never for production.

### Gotcha: Keycloak "Verify Profile" blocks login for users missing a name

By default Keycloak's user-profile feature attaches a `VERIFY_PROFILE` required
action to any account missing `firstName`/`lastName`. Such a user is bounced to
a "Review your profile" page after entering credentials and **never reaches the
app's callback** — so it can look like an SSO failure when it's really Keycloak
holding the login. The imported `alice`/`bob` have names, so they're fine; if
you add test users via the admin console or API, give them first/last names (or
clear the required action) so the flow completes. Real Entra/Keycloak users
normally have these populated.

## Break-glass (local accounts always work)

Local username/password sign-in (`/auth/login`) is never removed — the seed
admin and any local account remain a break-glass path even if the IdP is down or
misconfigured. SSO can't take over a local account either: if an SSO login's
email already belongs to a local account, the login is refused
(`#sso_error=local_account`) and the local password stays the only way in.

## Group → role mapping

Admins get an **Access** tab in the app (visible only when your role is admin)
to add/remove mappings without touching the database. Under the hood it calls
`/idp-role-maps` (GET/POST/DELETE, admin-only). Each row maps one IdP group
identifier to a role and optionally a team:

```
POST /api/idp-role-maps
{ "idp_group_id": "/pentrack-admins", "label": "PenTrack Admins", "role": "admin" }
```

`idp_group_id` is whatever the provider puts in the groups claim:
- **Keycloak:** the group path, e.g. `/pentrack-admins`.
- **Entra:** the group **object-ID GUID**, e.g. `1f3a...`. (Configure the groups
  claim on the app registration; mind the >200-group overage behaviour.)

## Cutover to real Entra ID (production)

No code changes — only configuration. In the app registration:

- Redirect URI: `https://<your-host>/api/auth/sso/callback`
- Enable the **groups** claim (or switch the strategy if you later prefer App Roles).

Then set on the api container:

```
OIDC_ENABLED=true
OIDC_AUTHORITY=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_CLIENT_ID=<app-registration-client-id>
OIDC_CLIENT_SECRET=<client-secret>
OIDC_REDIRECT_URI=https://<your-host>/api/auth/sso/callback
OIDC_POST_LOGIN_REDIRECT=https://<your-host>/
OIDC_GROUPS_CLAIM=groups
```

Leave `OIDC_BOOTSTRAP_*` unset in production and create the real GUID→role
mappings through `/idp-role-maps`.
