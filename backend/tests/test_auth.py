import json
from io import BytesIO
from urllib.parse import parse_qs, urlparse
import unittest

from backend.app.auth import AuthError, OAuthClient, OAuthSettings, Session
from backend.app.config import (
    CONFIG_OAUTH_CLIENT_ID,
    CONFIG_OAUTH_CLIENT_SECRET,
    CONFIG_OAUTH_REDIRECT_URI,
    CONFIG_OAUTH_SCOPES,
    CONFIG_SESSION_SECRET,
    load_config,
)
from backend.app.main import create_app
from backend.app.provider import FixtureDocumentProvider
from backend.tests.test_configuration import configured_values


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def read(self):
        return self.payload


def invoke(app, path, *, method="GET", query="", body=b"", headers=None):
    captured = {}

    def start_response(status, response_headers):
        captured["status"] = status
        captured["headers"] = dict(response_headers)

    result = b"".join(app({
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "CONTENT_TYPE": "application/json" if body else "",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
        **{f"HTTP_{key.upper().replace('-', '_')}": value for key, value in (headers or {}).items()},
    }, start_response))
    payload = json.loads(result) if result else None
    return captured, payload


def auth_values():
    values = configured_values()
    values.update({
        CONFIG_OAUTH_CLIENT_ID: "client.apps.googleusercontent.com",
        CONFIG_OAUTH_CLIENT_SECRET: "synthetic-client-secret",
        CONFIG_OAUTH_REDIRECT_URI: "http://localhost:8000/auth/google/callback",
        CONFIG_OAUTH_SCOPES: "openid email https://www.googleapis.com/auth/drive.file",
        CONFIG_SESSION_SECRET: "synthetic-session-secret",
    })
    return values


class AuthBoundaryTest(unittest.TestCase):
    def configured_app(self, opener):
        app = create_app(load_config(auth_values()).config, FixtureDocumentProvider())
        app._oauth = OAuthClient(
            OAuthSettings(
                "client.apps.googleusercontent.com",
                "synthetic-client-secret",
                "http://localhost:8000/auth/google/callback",
                ("openid", "email", "https://www.googleapis.com/auth/drive.file"),
                "synthetic-session-secret",
            ),
            opener=opener,
        )
        return app

    def test_start_redirects_without_exposing_client_secret(self):
        app = self.configured_app(lambda request, timeout: FakeResponse({}))
        status, body = invoke(app, "/auth/google")
        self.assertEqual(status["status"], "302 Found")
        self.assertIsNone(body)
        location = status["headers"]["Location"]
        self.assertEqual(urlparse(location).hostname, "accounts.google.com")
        self.assertNotIn("synthetic-client-secret", location)
        self.assertIn("state", parse_qs(urlparse(location).query))

    def test_invalid_state_is_rejected_and_valid_callback_creates_session(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            if request.full_url.endswith("userinfo"):
                return FakeResponse({"sub": "user-123", "email": "synthetic@example.test"})
            return FakeResponse({"access_token": "synthetic-access", "refresh_token": "synthetic-refresh", "expires_in": 3600})

        app = self.configured_app(opener)
        status, _ = invoke(app, "/auth/google/callback", query="state=bad&code=synthetic-code")
        self.assertEqual(status["status"], "400 Bad Request")

        start, _ = invoke(app, "/auth/google")
        state = parse_qs(urlparse(start["headers"]["Location"]).query)["state"][0]
        callback, _ = invoke(app, "/auth/google/callback", query=f"state={state}&code=synthetic-code")
        self.assertEqual(callback["status"], "302 Found")
        self.assertEqual(callback["headers"]["Location"], "http://localhost:3000")
        cookie = callback["headers"]["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertNotIn("synthetic-access", cookie)
        self.assertNotIn("synthetic-refresh", cookie)
        self.assertEqual(len(calls), 2)

        session, payload = invoke(app, "/api/session", headers={"Cookie": cookie})
        self.assertEqual(session["status"], "200 OK")
        self.assertEqual(payload["user"]["id"], "user-123")

        connected, payload = invoke(
            app,
            "/api/template/connect",
            method="POST",
            body=json.dumps({"url": "https://docs.google.com/document/d/fixture-template/edit"}).encode(),
            headers={"Cookie": cookie},
        )
        self.assertEqual(connected["status"], "200 OK")
        self.assertTrue(payload["selection_token"].startswith("tpl_"))

        other_session = app._sessions.put(Session("other-user", "other@example.test", "other-access", None, 9_999_999_999, 0))
        foreign, foreign_payload = invoke(
            app,
            "/api/invoices/preview",
            method="POST",
            body=b"{}",
            headers={"Cookie": f"invoice_session={other_session}", "X-Template-Selection": payload["selection_token"]},
        )
        self.assertEqual(foreign["status"], "400 Bad Request")
        self.assertEqual(foreign_payload["error"]["code"], "template_not_selected")

        logout, _ = invoke(app, "/auth/logout", method="POST", headers={"Cookie": cookie})
        self.assertEqual(logout["status"], "204 No Content")
        protected, payload = invoke(app, "/api/template/fields")
        self.assertEqual(protected["status"], "401 Unauthorized")
        self.assertEqual(payload["error"]["code"], "authentication_required")

    def test_denied_consent_explains_test_user_configuration_without_echoing_provider_data(self):
        app = self.configured_app(lambda request, timeout: FakeResponse({}))
        start, _ = invoke(app, "/auth/google")
        state = parse_qs(urlparse(start["headers"]["Location"]).query)["state"][0]
        status, payload = invoke(app, "/auth/google/callback", query=f"state={state}&error=access_denied")
        self.assertEqual(status["status"], "400 Bad Request")
        self.assertEqual(payload["error"]["code"], "authorization_denied")
        self.assertIn("approved", payload["error"]["message"])
        self.assertNotIn("access_denied", json.dumps(payload))

    def test_oauth_client_never_puts_tokens_in_userinfo_url(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            if request.full_url.endswith("userinfo"):
                return FakeResponse({"sub": "user-123"})
            return FakeResponse({"access_token": "synthetic-access", "expires_in": 3600})

        client = OAuthClient(OAuthSettings("id", "secret", "http://localhost/callback", ("openid",), "session"), opener=opener)
        client.exchange_code("synthetic-code")
        self.assertNotIn("synthetic-access", requests[-1].full_url)
        self.assertEqual(requests[-1].headers["Authorization"], "Bearer synthetic-access")

    def test_refresh_rotates_only_the_access_token_and_keeps_refresh_token_server_side(self):
        def opener(request, timeout):
            return FakeResponse({"access_token": "refreshed-access", "expires_in": 3600})

        client = OAuthClient(OAuthSettings("id", "secret", "http://localhost/callback", ("openid",), "session"), opener=opener)
        session = Session("user-123", None, "expired-access", "synthetic-refresh", 9_999_999_999, 10, 1)
        refreshed = client.refresh(session)
        self.assertEqual(refreshed.access_token, "refreshed-access")
        self.assertEqual(refreshed.refresh_token, "synthetic-refresh")
        self.assertEqual(refreshed.expires_at, session.expires_at)

    def test_invalid_refresh_token_is_classified_as_revoked_authorization(self):
        def opener(request, timeout):
            return FakeResponse({"error": "invalid_grant"})

        client = OAuthClient(OAuthSettings("id", "secret", "http://localhost/callback", ("openid",), "session"), opener=opener)
        with self.assertRaisesRegex(AuthError, "authorization_revoked"):
            client.refresh(Session("user-123", None, "access", "refresh", 9_999_999_999, 10, 1))

    def test_expiring_session_refreshes_before_protected_request(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            return FakeResponse({"access_token": "refreshed-access", "expires_in": 3600})

        app = self.configured_app(opener)
        session_id = app._sessions.put(Session("user-123", None, "expired-access", "synthetic-refresh", 9_999_999_999, 10, 1))
        status, payload = invoke(app, "/api/session", headers={"Cookie": f"invoice_session={session_id}"})
        self.assertEqual(status["status"], "200 OK")
        self.assertTrue(payload["authenticated"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(app._sessions.get(session_id).access_token, "refreshed-access")
