"""Security tests for diagnostics redaction."""
from __future__ import annotations

import unittest

from kyth_shared.diagnostics_scrub import scrub_logs


class TestDiagnosticsScrub(unittest.TestCase):
    def test_redacts_credentials_headers_and_structured_tokens(self):
        secrets = (
            "Authorization: Bearer bearer-secret\n"
            "Cookie: session=browser-secret; theme=dark\n"
            'oauth={"access_token":"access-secret","refresh_token":"refresh-secret"}\n'
            "password=hunter2 api_key=api-secret\n"
            "command --cookie cli-secret --token=flag-secret\n"
        )
        scrubbed = scrub_logs(secrets)
        for secret in (
            "bearer-secret", "browser-secret", "access-secret", "refresh-secret",
            "hunter2", "api-secret", "cli-secret", "flag-secret",
        ):
            self.assertNotIn(secret, scrubbed)

    def test_redacts_private_keys_url_secrets_and_network_identifiers(self):
        key_begin = "-----BEGIN " + "PRIVATE KEY-----"
        key_end = "-----END " + "PRIVATE KEY-----"
        report = (
            f"{key_begin}\nprivate-material\n{key_end}\n"
            "https://alice:password@example.test/path?access_token=query-secret&safe=yes\n"
            "IPv6 2001:db8:85a3::8a2e:370:7334 IPv4 192.0.2.10\n"
            "home=/var/home/alice/project\n"
        )
        scrubbed = scrub_logs(report)
        for secret in (
            "private-material", "alice:password", "query-secret",
            "2001:db8:85a3::8a2e:370:7334", "192.0.2.10", "/var/home/alice",
        ):
            self.assertNotIn(secret, scrubbed)

    def test_rejects_non_text_reports(self):
        with self.assertRaises(TypeError):
            scrub_logs(None)  # type: ignore[arg-type]
