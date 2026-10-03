# Google OAuth setup

This document is a deployment checklist. Replace every placeholder through the
deployment secret/configuration system; never commit client secrets, refresh
tokens, user data, or real document identifiers.

## Google Cloud project

For each environment, the platform owner creates or selects one Google Cloud
project and records only its non-secret project identifier:

1. Enable Google Drive API and Google Docs API.
2. Configure an OAuth consent screen for the application name and support contact.
3. Add only approved test users while the consent screen is in testing status.
4. Create a Web application OAuth client.
5. Register the exact callback URI, including scheme, host, port, path, and
   trailing-slash behavior. The local placeholder is:
   `http://localhost:8000/auth/google/callback`.
6. Register the browser origin used by the deployment. The local placeholder is:
   `http://localhost:3000`.

The client ID, client secret, session secret, and OAuth encryption material are
secret-managed configuration. They must not be placed in source control, URLs,
logs, browser storage, or issue comments.

## Scopes and selection boundary

The sign-in request uses:

- `openid` to establish the stable Google subject used as the internal user key;
- `email` and optionally `profile` for the account indicator shown in the UI;
- `https://www.googleapis.com/auth/drive.file` for per-file Drive access.

The backend exchanges the authorization code and keeps access/refresh tokens on
the server. The browser receives only the session cookie. `drive.file` is a
per-file boundary; it does not grant arbitrary Drive browsing. A future Picker
integration should pass the selected file ID to the backend, which must still
verify that the authenticated user can read that exact Google Docs file.

Until Picker is configured, the pasted-link flow is retained as a compatibility
path. The backend accepts only canonical Google Docs URLs and verifies the file
type/access through the signed-in user’s provider. Unsupported, inaccessible,
trashed, or non-Docs files return safe actionable errors.

## Environment configuration

Use the secret manager or deployment environment for:

```text
GOOGLE_CLOUD_PROJECT_ID=<project-id>
GOOGLE_OAUTH_CLIENT_ID=<web-client-id>
GOOGLE_OAUTH_CLIENT_SECRET=<secret-manager-value>
GOOGLE_OAUTH_REDIRECT_URI=<exact-registered-callback>
GOOGLE_OAUTH_SCOPES=openid,email,profile,https://www.googleapis.com/auth/drive.file
GOOGLE_PICKER_API_KEY=<restricted-browser-key-if-picker-is-enabled>
SESSION_SECRET=<secret-manager-value>
OAUTH_TOKEN_ENCRYPTION_KEY=<secret-manager-value-for-follow-up-24>
```

The current application validates the OAuth client, callback, scopes, and session
secret. Durable encrypted token storage is intentionally separate work under
#TASK-24; until that is deployed, sessions are process-local and restarting the
backend requires sign-in again.

## Disposable verification checklist

Use a test Google account and a disposable Google Doc only:

1. Open `/auth/google` and verify the consent page shows the expected account and
   scopes.
2. Complete consent and verify the callback redirects to the app without tokens
   in the URL or cookie.
3. Verify `/api/session` reports the account, then connect the disposable Doc.
4. Verify a second test account cannot reuse the first account’s selection token.
5. Revoke the app in Google account permissions; confirm the next protected
   operation returns a safe reauthorization path.
6. Test denied consent, expired state, mismatched redirect URI, inaccessible file,
   trashed file, and provider timeout.
7. Remove the disposable document and test account access when verification ends.

Record only status codes, safe error classes, timings, and aggregate cleanup
results. Do not retain consent screenshots containing account details, document
IDs, tokens, or invoice data.

## `403 access_denied` during testing

If Google says the app is available only to developer-approved testers, open the
project’s OAuth consent screen in Google Cloud Console and add the exact Google
account email under **Test users**. Save the change, then restart the authorization
flow. Do not try to work around the restriction by changing the redirect URI or
placing credentials in the browser. Testing-mode projects are intended for a
limited allowlist; publish and complete Google verification only when the app is
ready for users outside that allowlist.

## Rotation and emergency disablement

Change the OAuth client secret and session secret through the secret manager,
restart the service, and verify readiness plus a new disposable sign-in. If the
client is compromised, disable the client, revoke its grants, disable generation
at the edge, and follow [_docs/credential-rotation.md](_docs/credential-rotation.md).
