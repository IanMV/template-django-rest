from django.test import SimpleTestCase

from core.shared.security import record_event


class SecurityLogTests(SimpleTestCase):
    def test_security_events_only_accept_fixed_values(self):
        for event, outcome in (
            ("person@example.com", "SUCCESS"),
            ("LOGIN", "raw-password"),
        ):
            with self.subTest(event=event), self.assertRaises(ValueError):
                record_event(event, outcome)

    def test_security_event_has_no_user_or_request_payload(self):
        with self.assertLogs("core.security", level="INFO") as logs:
            record_event("LOGIN", "FAILURE")
        self.assertEqual(logs.records[0].getMessage(), "Security event: LOGIN FAILURE")
