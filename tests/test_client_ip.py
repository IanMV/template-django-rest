from django.test import RequestFactory, SimpleTestCase, override_settings

from core.shared.client_ip import get_client_ip


class ClientIPTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request(self, remote="192.0.2.10", forwarded="198.51.100.1, 203.0.113.2"):
        return self.factory.get(
            "/", REMOTE_ADDR=remote, HTTP_X_FORWARDED_FOR=forwarded
        )

    @override_settings(NUM_PROXIES=0)
    def test_direct_request_ignores_forwarded_header(self):
        self.assertEqual(get_client_ip(self.request()), "192.0.2.10")

    @override_settings(NUM_PROXIES=1)
    def test_single_proxy_uses_rightmost_header_address(self):
        self.assertEqual(get_client_ip(self.request()), "203.0.113.2")

    @override_settings(NUM_PROXIES=2)
    def test_two_proxies_ignore_spoofed_leftmost_address(self):
        request = self.request(forwarded="1.2.3.4, 198.51.100.1, 203.0.113.2")
        self.assertEqual(get_client_ip(request), "198.51.100.1")

    @override_settings(NUM_PROXIES=2)
    def test_short_chain_uses_remote_address(self):
        self.assertEqual(
            get_client_ip(self.request(forwarded="1.2.3.4")), "192.0.2.10"
        )

    @override_settings(NUM_PROXIES=1)
    def test_malformed_header_uses_remote_address(self):
        self.assertEqual(
            get_client_ip(self.request(forwarded="invalid")), "192.0.2.10"
        )

    @override_settings(NUM_PROXIES=0)
    def test_malformed_remote_address_is_not_used(self):
        self.assertIsNone(get_client_ip(self.request(remote="invalid")))
