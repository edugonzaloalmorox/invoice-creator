import json
from io import BytesIO
from urllib.parse import parse_qs, urlparse
import unittest
from unittest.mock import Mock, patch

from backend.app.auth import AuthError, OAuthClient, OAuthSettings, Session, SessionStore
from backend.app.config import (
    CONFIG_OAUTH_CLIENT_ID,
    CONFIG_OAUTH_CLIENT_SECRET,
    CONFIG_OAUTH_REDIRECT_URI,
    CONFIG_OAUTH_SCOPES,
    CONFIG_SESSION_SECRET,
    load_config,
)
from backend.app.google_provider import GoogleDocumentProvider
from backend.app.main import create_app
from backend.app.provider import FixtureDocumentProvider
from backend.tests.test_configuration import configured_values
from backend.tests.test_preview import invoice_body
from backend.tests.test_generate import call_raw


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
        CONFIG_OAUTH_SCOPES: "openid email https://www.googleapis.com/auth/documents https://www.googleapis.com/auth/drive.file",
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
                ("openid", "email", "https://www.googleapis.com/auth/documents", "https://www.googleapis.com/auth/drive.file"),
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
        self.assertIn("Max-Age=3600", cookie)
        self.assertIn("Path=/", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertNotIn("Secure", cookie)
        self.assertNotIn("synthetic-access", cookie)
        self.assertNotIn("synthetic-refresh", cookie)
        self.assertEqual(len(calls), 2)

        preflight, _ = invoke(
            app,
            "/api/template/connect",
            method="OPTIONS",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(preflight["status"], "204 No Content")
        self.assertEqual(preflight["headers"]["Access-Control-Allow-Origin"], "http://localhost:3000")
        self.assertEqual(preflight["headers"]["Access-Control-Allow-Credentials"], "true")

        session, payload = invoke(app, "/api/session", headers={"Cookie": cookie})
        self.assertEqual(session["status"], "200 OK")
        self.assertEqual(payload["user"]["id"], "user-123")

        connected, payload = invoke(
            app,
            "/api/template/connect",
            method="POST",
            body=json.dumps({"url": "https://docs.google.com/document/d/fixture-template/edit"}).encode(),
            headers={"Cookie": cookie, "Origin": "http://localhost:3000"},
        )
        self.assertEqual(connected["status"], "200 OK")
        self.assertEqual(connected["headers"]["Access-Control-Allow-Origin"], "http://localhost:3000")
        self.assertEqual(connected["headers"]["Access-Control-Allow-Credentials"], "true")
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

    def test_authenticated_template_provider_uses_server_side_user_credentials(self):
        provider = GoogleDocumentProvider("/run/secrets/service-account.json", credentials=object())
        app = create_app(load_config(auth_values()).config, provider)
        session_id = app._sessions.put(Session("user-123", None, "synthetic-access", "synthetic-refresh", 9_999_999_999, 0))

        user_provider = app._provider_for({"HTTP_COOKIE": f"invoice_session={session_id}"})

        self.assertEqual(user_provider.credential_reference, "oauth://signed-in-user")
        self.assertEqual(user_provider._credentials.token, "synthetic-access")
        self.assertEqual(user_provider._credentials.refresh_token, "synthetic-refresh")

    def test_authenticated_preview_and_generation_use_one_temporary_document(self):
        provider = FixtureDocumentProvider()
        app = create_app(load_config(auth_values()).config, provider)
        session_id = app._sessions.put(Session("user-123", "synthetic@example.test", "synthetic-access", None, 9_999_999_999, 0))
        cookie = f"invoice_session={session_id}"
        headers = {"Cookie": cookie}

        connected, connection = invoke(
            app,
            "/api/template/connect",
            method="POST",
            body=json.dumps({"url": "https://docs.google.com/document/d/fixture-template/edit"}).encode(),
            headers=headers,
        )
        self.assertEqual(connected["status"], "200 OK")
        token = connection["selection_token"]
        headers["X-Template-Selection"] = token

        preview, _ = invoke(app, "/api/invoices/preview", method="POST", body=invoice_body(), headers=headers)
        self.assertEqual(preview["status"], "200 OK")
        generated, body = call_raw(app, invoice_body(), headers=headers)
        self.assertEqual(generated["status"], "200 OK")
        self.assertTrue(body.startswith(b"%PDF"))
        generation_calls = provider.calls[-5:]
        self.assertEqual([operation for operation, _ in generation_calls], ["copy_document", "replace_values", "verify_replacements", "export_pdf", "delete_document"])
        self.assertEqual(generation_calls[0][1], "fixture-template")
        self.assertEqual({document_id for _, document_id in generation_calls[1:]}, {"fixture-copy-1"})
        self.assertNotIn("synthetic-access", body.decode("latin1"))

    def test_authenticated_copy_not_found_is_safe_and_stops_before_mutation(self):
        provider = FixtureDocumentProvider(failures={"copy_document": "template_not_found"})
        app = create_app(load_config(auth_values()).config, provider)
        session_id = app._sessions.put(Session("user-123", "synthetic@example.test", "synthetic-access", None, 9_999_999_999, 0))
        headers = {"Cookie": f"invoice_session={session_id}"}

        connected, connection = invoke(
            app,
            "/api/template/connect",
            method="POST",
            body=json.dumps({"url": "https://docs.google.com/document/d/fixture-template/edit"}).encode(),
            headers=headers,
        )
        self.assertEqual(connected["status"], "200 OK")
        headers["X-Template-Selection"] = connection["selection_token"]

        preview, _ = invoke(app, "/api/invoices/preview", method="POST", body=invoice_body(), headers=headers)
        self.assertEqual(preview["status"], "200 OK")
        generated, payload = invoke(app, "/api/invoices/generate", method="POST", body=invoice_body(), headers=headers)
        self.assertEqual(generated["status"], "404 Not Found")
        self.assertEqual(payload["error"]["code"], "template_not_found")
        self.assertNotIn("synthetic", json.dumps(payload))
        self.assertEqual([operation for operation, _ in provider.calls], ["read_template", "copy_document"])

    def test_authenticated_connect_reads_google_template_and_returns_sanitized_fields(self):
        drive = Mock()
        drive.files.return_value.get.return_value.execute.return_value = {
            "id": "authorized-template-id",
            "name": "Synthetic invoice template",
            "mimeType": "application/vnd.google-apps.document",
            "trashed": False,
        }
        docs = Mock()
        docs.documents.return_value.get.return_value.execute.return_value = {
            "title": "Synthetic invoice template",
            "body": {"content": [{"paragraph": {"elements": [{"textRun": {"content": "{{days_worked}}"}}]}}]},
        }
        user_provider = GoogleDocumentProvider(
            "oauth://signed-in-user",
            drive_service=drive,
            docs_service=docs,
            credentials=object(),
        )
        app = create_app(load_config(auth_values()).config, GoogleDocumentProvider("/run/secrets/service-account.json", credentials=object()))
        session_id = app._sessions.put(Session("user-123", None, "synthetic-access", "synthetic-refresh", 9_999_999_999, 0))

        with patch.object(GoogleDocumentProvider, "for_user_session", return_value=user_provider) as factory:
            status, payload = invoke(
                app,
                "/api/template/connect",
                method="POST",
                body=json.dumps({"url": "https://docs.google.com/document/d/authorized-template-id/edit"}).encode(),
                headers={"Cookie": f"invoice_session={session_id}"},
            )

        self.assertEqual(status["status"], "200 OK")
        self.assertEqual(payload["template"]["name"], "Synthetic invoice template")
        self.assertNotIn("authorized-template-id", json.dumps(payload))
        self.assertNotIn("{{days_worked}}", json.dumps(payload))
        self.assertEqual(factory.call_args.kwargs["access_token"], "synthetic-access")
        drive.files.return_value.get.assert_not_called()
        docs.documents.return_value.get.assert_called_once_with(
            documentId="authorized-template-id", includeTabsContent=True
        )

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

    def test_session_cookie_security_and_rotation_contract(self):
        store = SessionStore("synthetic-session-secret")
        development = store.cookie_header("session-one", secure=False)
        production = store.cookie_header("session-two", secure=True)

        self.assertIn("Max-Age=3600", development)
        self.assertIn("HttpOnly", development)
        self.assertIn("SameSite=Lax", development)
        self.assertNotIn("Secure", development)
        self.assertIn("Secure", production)
        self.assertNotEqual(store.put(Session("user", None, "access", None, 9_999_999_999, 0)), store.put(Session("user", None, "access", None, 9_999_999_999, 0)))
