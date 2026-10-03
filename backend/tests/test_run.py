import unittest

from backend.run import redact_request_line


class AccessLogRedactionTest(unittest.TestCase):
    def test_query_values_are_removed_from_access_log_request_line(self):
        line = "GET /auth/google/callback?code=synthetic-code&state=synthetic-state HTTP/1.1"
        self.assertEqual(redact_request_line(line), "GET /auth/google/callback HTTP/1.1")

    def test_malformed_request_line_is_left_unchanged(self):
        self.assertEqual(redact_request_line("not-a-request-line"), "not-a-request-line")
