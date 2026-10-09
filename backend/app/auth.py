"""Small, dependency-free Google OAuth authorization-code boundary."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
SESSION_COOKIE = "invoice_session"
SESSION_TTL_SECONDS = 3600
STATE_TTL_SECONDS = 600


class AuthError(Exception):
    """An OAuth failure that is safe to map to a public error code."""

    def __init__(self, code: str, *, retryable: bool = False):
        """Create an OAuth error with a stable public classification."""

        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class OAuthSettings:
    """Configuration required to perform Google OAuth exchanges."""

    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: tuple[str, ...]
    session_secret: str


@dataclass(slots=True)
class Session:
    """Server-side session state and token-expiry metadata."""

    user_id: str
    email: str | None
    access_token: str
    refresh_token: str | None
    expires_at: float
    created_at: float
    access_expires_at: float | None = None


def _safe_json(response) -> dict:
    """Decode a provider response or raise a sanitized availability error."""

    try:
        body = response.read()
        payload = json.loads(body)
    except (OSError, ValueError, TypeError, UnicodeDecodeError) as error:
        raise AuthError("provider_unavailable", retryable=True) from error
    if not isinstance(payload, dict):
        raise AuthError("provider_unavailable", retryable=True)
    return payload


class OAuthClient:
    """Google OAuth calls. The opener is injectable so tests never use a network."""

    def __init__(self, settings: OAuthSettings, *, opener=urlopen):
        """Create a client using an injectable HTTP opener for deterministic tests."""

        self.settings = settings
        self._opener = opener

    def authorization_url(self, state: str) -> str:
        """Build the Google authorization URL for a signed-in browser flow."""

        return f"{AUTHORIZATION_ENDPOINT}?{urlencode({
            'client_id': self.settings.client_id,
            'redirect_uri': self.settings.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.settings.scopes),
            'access_type': 'offline',
            'prompt': 'consent',
            'state': state,
        })}"

    def exchange_code(self, code: str) -> Session:
        """Exchange an authorization code and load the associated user identity."""

        body = urlencode({
            "code": code,
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
            "redirect_uri": self.settings.redirect_uri,
            "grant_type": "authorization_code",
        }).encode()
        request = Request(TOKEN_ENDPOINT, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            payload = _safe_json(self._opener(request, timeout=10))
        except HTTPError as error:
            raise AuthError("authorization_denied") if error.code in {400, 401} else AuthError("provider_unavailable", retryable=True)
        except (OSError, URLError) as error:
            raise AuthError("provider_unavailable", retryable=True) from error
        if payload.get("error"):
            code_name = payload.get("error")
            raise AuthError("authorization_denied" if code_name in {"invalid_grant", "access_denied"} else "provider_unavailable", retryable=code_name not in {"invalid_grant", "access_denied"})
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AuthError("provider_unavailable", retryable=True)
        user = self.userinfo(access_token)
        user_id = user.get("sub")
        if not isinstance(user_id, str) or not user_id:
            raise AuthError("identity_unavailable")
        expires_in = payload.get("expires_in", 3600)
        now = time.time()
        try:
            access_expires_at = now + max(1, int(expires_in))
        except (TypeError, ValueError):
            access_expires_at = now + 3600
        return Session(user_id, user.get("email") if isinstance(user.get("email"), str) else None, access_token, payload.get("refresh_token"), now + SESSION_TTL_SECONDS, now, access_expires_at)

    def refresh(self, session: Session) -> Session:
        """Refresh an expiring access token while preserving session ownership."""

        if not session.refresh_token:
            raise AuthError("authorization_revoked")
        body = urlencode({
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
            "refresh_token": session.refresh_token,
            "grant_type": "refresh_token",
        }).encode()
        request = Request(TOKEN_ENDPOINT, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            payload = _safe_json(self._opener(request, timeout=10))
        except HTTPError as error:
            if error.code in {400, 401}:
                raise AuthError("authorization_revoked") from error
            raise AuthError("provider_unavailable", retryable=True) from error
        except (OSError, URLError) as error:
            raise AuthError("provider_unavailable", retryable=True) from error
        if payload.get("error"):
            code_name = payload.get("error")
            raise AuthError("authorization_revoked" if code_name == "invalid_grant" else "provider_unavailable", retryable=code_name != "invalid_grant")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AuthError("provider_unavailable", retryable=True)
        now = time.time()
        try:
            access_expires_at = now + max(1, int(payload.get("expires_in", 3600)))
        except (TypeError, ValueError):
            access_expires_at = now + 3600
        return Session(session.user_id, session.email, access_token, session.refresh_token, session.expires_at, session.created_at, access_expires_at)

    def userinfo(self, access_token: str) -> dict:
        """Fetch the authenticated user profile without exposing token data."""

        request = Request(USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"})
        try:
            payload = _safe_json(self._opener(request, timeout=10))
        except HTTPError as error:
            if error.code in {401, 403}:
                raise AuthError("authorization_revoked") from error
            raise AuthError("provider_unavailable", retryable=True) from error
        except (OSError, URLError) as error:
            raise AuthError("provider_unavailable", retryable=True) from error
        if payload.get("error"):
            raise AuthError("authorization_revoked")
        return payload


class SessionStore:
    """Process-local sessions until durable encrypted storage (#24) is added."""

    def __init__(self, secret: str, *, now=time.time):
        """Create an in-memory session store with an injectable clock."""

        self._secret = secret.encode()
        self._now = now
        self._sessions: dict[str, Session] = {}
        self._states: dict[str, float] = {}

    def start(self) -> str:
        """Create and retain a short-lived OAuth state value."""

        self._purge()
        state = secrets.token_urlsafe(24)
        self._states[state] = self._now() + STATE_TTL_SECONDS
        return state

    def consume_state(self, state: str) -> bool:
        """Atomically validate and consume an OAuth state value."""

        self._purge()
        expiry = self._states.pop(state, None)
        return expiry is not None and expiry > self._now()

    def put(self, session: Session) -> str:
        """Store a session and return its opaque browser identifier."""

        self._purge()
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = session
        return session_id

    def replace(self, session_id: str, session: Session) -> None:
        """Replace an existing session without creating a new identifier."""

        if session_id in self._sessions:
            self._sessions[session_id] = session

    def get(self, session_id: str | None) -> Session | None:
        """Return a live session for an opaque identifier, if present."""

        self._purge()
        if not session_id:
            return None
        return self._sessions.get(session_id)

    def delete(self, session_id: str | None) -> None:
        """Remove a session identifier when one was supplied."""

        if session_id:
            self._sessions.pop(session_id, None)

    def cookie_header(self, session_id: str, *, secure: bool) -> str:
        """Build the security attributes for an authenticated session cookie."""

        cookie = SimpleCookie()
        cookie[SESSION_COOKIE] = session_id
        morsel = cookie[SESSION_COOKIE]
        morsel["path"] = "/"
        morsel["httponly"] = True
        morsel["samesite"] = "Lax"
        morsel["max-age"] = str(SESSION_TTL_SECONDS)
        if secure:
            morsel["secure"] = True
        return morsel.OutputString()

    def clear_cookie_header(self, *, secure: bool) -> str:
        """Build an expired cookie header that clears the browser session."""

        cookie = SimpleCookie()
        cookie[SESSION_COOKIE] = ""
        morsel = cookie[SESSION_COOKIE]
        morsel["path"] = "/"
        morsel["max-age"] = "0"
        morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        morsel["httponly"] = True
        morsel["samesite"] = "Lax"
        if secure:
            morsel["secure"] = True
        return morsel.OutputString()

    def session_id_from_environ(self, environ: dict) -> str | None:
        """Extract the configured session cookie from a WSGI environment."""

        cookie = SimpleCookie(environ.get("HTTP_COOKIE", ""))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _purge(self) -> None:
        """Discard expired OAuth states and sessions from process-local storage."""

        now = self._now()
        self._states = {state: expiry for state, expiry in self._states.items() if expiry > now}
        self._sessions = {sid: session for sid, session in self._sessions.items() if session.expires_at > now}
